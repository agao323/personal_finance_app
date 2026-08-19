/**
 * The browser half of the WebAuthn ceremonies.
 *
 * The server speaks JSON and the browser API speaks `ArrayBuffer`, so most of this
 * file is that translation. It is worth having in one place because getting it wrong
 * produces a ceremony that fails verification with no useful error — the buffers are
 * opaque, and "challenge mismatch" is the same message whether the challenge was
 * wrong or merely decoded wrong.
 *
 * Base64**url**, not base64: WebAuthn uses the URL-safe alphabet and omits padding.
 * Decoding with the standard alphabet appears to work on most values and fails on the
 * ones containing `-` or `_`, which is roughly one ceremony in eight.
 */

export interface CeremonyOptions {
  options: Record<string, unknown>;
  challenge_id: string;
}

export class WebAuthnUnavailable extends Error {
  constructor() {
    super("This browser has no passkey support.");
    this.name = "WebAuthnUnavailable";
  }
}

export function isSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.PublicKeyCredential !== "undefined" &&
    Boolean(navigator.credentials)
  );
}

export function base64urlToBytes(value: string): Uint8Array {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

export function bytesToBase64url(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * Turn the server's JSON options into what `navigator.credentials` expects.
 *
 * Only the fields that are genuinely binary are converted. Walking the object and
 * decoding anything base64-shaped was rejected: a user's display name can look like
 * base64, and silently turning it into a buffer is a bug nobody would think to look
 * for.
 */
interface EncodedDescriptor {
  id: string;
  [key: string]: unknown;
}

/** The server's JSON, with the fields that are actually binary named as strings. */
interface EncodedCreationOptions {
  challenge: string;
  user: { id: string; [key: string]: unknown };
  excludeCredentials?: EncodedDescriptor[];
  [key: string]: unknown;
}

interface EncodedRequestOptions {
  challenge: string;
  allowCredentials?: EncodedDescriptor[];
  [key: string]: unknown;
}

export function toCreationOptions(
  options: Record<string, unknown>,
): PublicKeyCredentialCreationOptions {
  const raw = options as unknown as EncodedCreationOptions;
  return {
    ...raw,
    challenge: base64urlToBytes(raw.challenge),
    user: { ...raw.user, id: base64urlToBytes(raw.user.id) },
    excludeCredentials: (raw.excludeCredentials ?? []).map((credential) => ({
      ...credential,
      id: base64urlToBytes(credential.id),
    })),
  } as unknown as PublicKeyCredentialCreationOptions;
}

export function toRequestOptions(
  options: Record<string, unknown>,
): PublicKeyCredentialRequestOptions {
  const raw = options as unknown as EncodedRequestOptions;
  return {
    ...raw,
    challenge: base64urlToBytes(raw.challenge),
    allowCredentials: (raw.allowCredentials ?? []).map((credential) => ({
      ...credential,
      id: base64urlToBytes(credential.id),
    })),
  } as unknown as PublicKeyCredentialRequestOptions;
}

/** The registration response, in the JSON shape the server verifies. */
export function encodeRegistration(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: bytesToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bytesToBase64url(response.clientDataJSON),
      attestationObject: bytesToBase64url(response.attestationObject),
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

/** The assertion, in the JSON shape the server verifies. */
export function encodeAuthentication(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: bytesToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bytesToBase64url(response.clientDataJSON),
      authenticatorData: bytesToBase64url(response.authenticatorData),
      signature: bytesToBase64url(response.signature),
      userHandle: response.userHandle ? bytesToBase64url(response.userHandle) : null,
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

export async function createCredential(
  options: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  if (!isSupported()) throw new WebAuthnUnavailable();
  const credential = (await navigator.credentials.create({
    publicKey: toCreationOptions(options),
  })) as PublicKeyCredential | null;
  if (!credential) throw new Error("No passkey was created.");
  return encodeRegistration(credential);
}

export async function getCredential(
  options: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  if (!isSupported()) throw new WebAuthnUnavailable();
  const credential = (await navigator.credentials.get({
    publicKey: toRequestOptions(options),
  })) as PublicKeyCredential | null;
  if (!credential) throw new Error("No passkey was offered.");
  return encodeAuthentication(credential);
}
