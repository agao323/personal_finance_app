import { describe, expect, it, vi } from "vitest";

import {
  WebAuthnUnavailable,
  base64urlToBytes,
  bytesToBase64url,
  createCredential,
  encodeAuthentication,
  encodeRegistration,
  getCredential,
  isSupported,
  toCreationOptions,
  toRequestOptions,
} from "@/lib/webauthn";

function buffer(...bytes: number[]): ArrayBuffer {
  return Uint8Array.from(bytes).buffer;
}

describe("base64url", () => {
  it("round-trips arbitrary bytes", () => {
    const bytes = Uint8Array.from([0, 1, 250, 251, 252, 253, 254, 255]);

    expect(base64urlToBytes(bytesToBase64url(bytes.buffer))).toEqual(bytes);
  });

  it("uses the URL-safe alphabet", () => {
    // These bytes encode to "+/" in standard base64. Decoding a WebAuthn value with
    // the standard alphabet works on most inputs and fails on roughly one in eight,
    // which is a maddening way to find a bug.
    const encoded = bytesToBase64url(buffer(255, 239, 190));

    expect(encoded).not.toContain("+");
    expect(encoded).not.toContain("/");
    expect(encoded).not.toContain("=");
  });

  it("decodes an unpadded value", () => {
    expect(base64urlToBytes("AQ")).toEqual(Uint8Array.from([1]));
  });
});

describe("toCreationOptions", () => {
  it("decodes the challenge and the user id, and nothing else", () => {
    // Walking the object decoding anything base64-shaped would turn a display name
    // into a buffer — a bug nobody would think to look for.
    const options = toCreationOptions({
      challenge: "AQID",
      rp: { id: "localhost", name: "Personal finance" },
      user: { id: "BAUG", name: "owner@example.invalid", displayName: "Owner" },
    });

    expect(options.challenge).toEqual(Uint8Array.from([1, 2, 3]));
    expect(options.user.id).toEqual(Uint8Array.from([4, 5, 6]));
    expect(options.user.displayName).toBe("Owner");
    expect(options.rp.id).toBe("localhost");
  });

  it("decodes each excluded credential id", () => {
    const options = toCreationOptions({
      challenge: "AQID",
      user: { id: "BAUG" },
      excludeCredentials: [{ id: "AQ", type: "public-key" }],
    });

    expect(options.excludeCredentials?.[0].id).toEqual(Uint8Array.from([1]));
  });

  it("copes with no excluded credentials", () => {
    const options = toCreationOptions({ challenge: "AQID", user: { id: "BAUG" } });

    expect(options.excludeCredentials).toEqual([]);
  });
});

describe("toRequestOptions", () => {
  it("decodes the challenge", () => {
    expect(toRequestOptions({ challenge: "AQID" }).challenge).toEqual(Uint8Array.from([1, 2, 3]));
  });
});

describe("encodeRegistration", () => {
  it("produces the JSON shape the server verifies", () => {
    const credential = {
      id: "abc",
      rawId: buffer(1, 2),
      type: "public-key",
      response: { clientDataJSON: buffer(3), attestationObject: buffer(4) },
      getClientExtensionResults: () => ({}),
    } as unknown as PublicKeyCredential;

    expect(encodeRegistration(credential)).toEqual({
      id: "abc",
      rawId: "AQI",
      type: "public-key",
      response: { clientDataJSON: "Aw", attestationObject: "BA" },
      clientExtensionResults: {},
    });
  });
});

describe("encodeAuthentication", () => {
  it("includes the user handle when the authenticator supplies one", () => {
    const credential = {
      id: "abc",
      rawId: buffer(1),
      type: "public-key",
      response: {
        clientDataJSON: buffer(2),
        authenticatorData: buffer(3),
        signature: buffer(4),
        userHandle: buffer(5),
      },
      getClientExtensionResults: () => ({}),
    } as unknown as PublicKeyCredential;

    expect(encodeAuthentication(credential)).toMatchObject({
      response: { userHandle: "BQ" },
    });
  });

  it("sends null rather than omitting an absent user handle", () => {
    const credential = {
      id: "abc",
      rawId: buffer(1),
      type: "public-key",
      response: {
        clientDataJSON: buffer(2),
        authenticatorData: buffer(3),
        signature: buffer(4),
        userHandle: null,
      },
      getClientExtensionResults: () => ({}),
    } as unknown as PublicKeyCredential;

    expect(encodeAuthentication(credential)).toMatchObject({
      response: { userHandle: null },
    });
  });
});

describe("support detection", () => {
  it("is false in a browser with no PublicKeyCredential", () => {
    // jsdom has none, which is the case worth handling: a sign-in page that renders
    // a button doing nothing is worse than one that says why.
    expect(isSupported()).toBe(false);
  });

  it("refuses to start a ceremony it cannot finish", async () => {
    await expect(createCredential({})).rejects.toBeInstanceOf(WebAuthnUnavailable);
    await expect(getCredential({})).rejects.toBeInstanceOf(WebAuthnUnavailable);
  });

  it("is true once the API is present", () => {
    vi.stubGlobal("PublicKeyCredential", class {});
    vi.stubGlobal("navigator", { credentials: {} });

    expect(isSupported()).toBe(true);

    vi.unstubAllGlobals();
  });
});
