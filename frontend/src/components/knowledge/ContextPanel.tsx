import { useState } from 'react';
import type {
  KnowledgeEventAttachment,
  KnowledgeEventContextMessage,
  KnowledgeSourceEvent,
} from '../../lib/types';

function formatDate(value: string | null | undefined) {
  if (!value) {
    return 'Unknown time';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}

function normalizeMessages(sourceEvent: KnowledgeSourceEvent): KnowledgeEventContextMessage[] {
  const messages = sourceEvent.metadata?.context_messages;
  return Array.isArray(messages) ? messages : [];
}

function normalizeAttachments(sourceEvent: KnowledgeSourceEvent): KnowledgeEventAttachment[] {
  const attachments = sourceEvent.metadata?.attachments;
  return Array.isArray(attachments) ? attachments : [];
}

export default function ContextPanel({ sourceEvents }: { sourceEvents: KnowledgeSourceEvent[] }) {
  const [expanded, setExpanded] = useState(false);

  const hasSourceEvents = sourceEvents.length > 0;
  const hasCapturedContext = sourceEvents.some((sourceEvent) => {
    return normalizeMessages(sourceEvent).length > 0 || normalizeAttachments(sourceEvent).length > 0;
  });

  let summaryText = 'No linked source events yet.';
  if (hasSourceEvents && hasCapturedContext) {
    summaryText = 'Surrounding context was captured for at least one linked source event.';
  } else if (hasSourceEvents) {
    summaryText = 'A source event is linked, but no surrounding Slack context was captured.';
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-medium text-gray-900">Decision Context</h3>
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                hasCapturedContext
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-gray-100 text-gray-600'
              }`}
            >
              {hasCapturedContext ? 'Context Captured' : 'No Expanded Context'}
            </span>
          </div>
          <p className="text-sm text-gray-500">{summaryText}</p>
        </div>

        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          disabled={!hasSourceEvents}
          className={`text-sm px-3 py-2 rounded-md border transition-colors ${
            hasSourceEvents
              ? 'border-gray-300 text-gray-700 hover:bg-gray-50'
              : 'border-gray-200 text-gray-400 cursor-not-allowed'
          }`}
        >
          {expanded ? 'Hide Context' : 'Show Context'}
        </button>
      </div>

      {expanded && (
        <div className="mt-5 pt-5 border-t border-gray-100 space-y-4">
          {!hasSourceEvents && (
            <p className="text-sm text-gray-500">No source events are linked to this decision yet.</p>
          )}

          {sourceEvents.map((sourceEvent) => {
            const contextMessages = normalizeMessages(sourceEvent);
            const attachments = normalizeAttachments(sourceEvent);
            const actorName =
              (sourceEvent.metadata?.actor_display_name as string | undefined) ||
              sourceEvent.actor_name ||
              'Unknown';

            return (
              <section key={sourceEvent.id} className="rounded-lg border border-gray-200 p-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 font-medium">
                      {sourceEvent.source}
                    </span>
                    {sourceEvent.relationship && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                        {sourceEvent.relationship}
                      </span>
                    )}
                    <span className="text-xs text-gray-400">{formatDate(sourceEvent.occurred_at)}</span>
                  </div>
                  <span className="text-xs text-gray-500">Author: {actorName}</span>
                </div>

                <div className="mb-4">
                  <h4 className="text-sm font-medium text-gray-700 mb-2">Trigger Event</h4>
                  <div className="rounded-md bg-gray-50 border border-gray-100 p-3 text-sm text-gray-700 whitespace-pre-wrap">
                    {sourceEvent.content || 'No event content captured.'}
                  </div>
                </div>

                <div className="space-y-3">
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-2">Surrounding Messages</h4>
                    {contextMessages.length === 0 && (
                      <p className="text-sm text-gray-500">
                        No surrounding Slack messages were captured for this source event.
                      </p>
                    )}
                    {contextMessages.length > 0 && (
                      <div className="space-y-2">
                        {contextMessages.map((message) => {
                          const isTrigger = message.ts === sourceEvent.source_id;
                          return (
                            <div
                              key={`${sourceEvent.id}-${message.ts}`}
                              className={`rounded-md border p-3 ${
                                isTrigger
                                  ? 'border-blue-200 bg-blue-50'
                                  : 'border-gray-100 bg-gray-50'
                              }`}
                            >
                              <div className="flex items-center justify-between gap-2 mb-1">
                                <span className="text-xs font-medium text-gray-700">
                                  {message.user_name || 'Unknown'}
                                </span>
                                {isTrigger && (
                                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium">
                                    Trigger
                                  </span>
                                )}
                              </div>
                              <p className="text-sm text-gray-700 whitespace-pre-wrap">
                                {message.text || 'No text captured.'}
                              </p>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-2">Attachments</h4>
                    {attachments.length === 0 && (
                      <p className="text-sm text-gray-500">No attachment metadata was captured.</p>
                    )}
                    {attachments.length > 0 && (
                      <div className="space-y-2">
                        {attachments.map((attachment) => {
                          const href = attachment.permalink || attachment.url_private;
                          const typeLabel = attachment.filetype || attachment.mimetype || 'file';

                          return (
                            <div
                              key={`${sourceEvent.id}-${attachment.id}`}
                              className="rounded-md border border-gray-100 bg-gray-50 p-3 text-sm"
                            >
                              {href ? (
                                <a
                                  href={href}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="font-medium text-blue-700 hover:text-blue-800"
                                >
                                  {attachment.name}
                                </a>
                              ) : (
                                <span className="font-medium text-gray-800">{attachment.name}</span>
                              )}
                              <p className="text-gray-500 mt-1">{typeLabel}</p>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
