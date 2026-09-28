"use client";

/** One conversation. The id is the route's; everything else is `Conversation`'s. */

import { useParams } from "next/navigation";

import { Conversation } from "@/components/advisor/conversation";

export default function ConversationPage() {
  const params = useParams<{ id: string }>();
  return <Conversation id={params.id} />;
}
