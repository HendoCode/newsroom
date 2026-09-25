"use client";

import * as React from "react";

import { DiffView } from "@/components/voice-kit/diff-view";
import { Button } from "@/components/ui/button";
import { TextArea } from "@/components/ui/textarea";
import { applyLessonRule } from "@/lib/voice-kit/lesson-preview";
import type { Lesson } from "@/lib/voice-kit/types";

/**
 * The proposed-lessons gate (cmw-ui-wireframes screen 11; D12; domain model §1.18;
 * cmw-lesson-lineage-impl): the machine proposes lessons by diffing final vs. published; a human
 * accepts/edits/rejects **in one click**, or in a batch. Each row previews the Git diff of the
 * rule about to land in `content-lessons.md`. The machine never self-commits — only `onAccept`
 * reaches Git.
 */
export function LessonsGate({
  lessons,
  currentLessonsFile = "",
  onAccept,
  onReject,
  onAcceptMany,
  onRejectMany,
  busyId,
  error,
}: {
  lessons: Lesson[];
  currentLessonsFile?: string;
  onAccept: (lessonId: string, ruleText?: string) => void;
  onReject: (lessonId: string) => void;
  onAcceptMany?: (lessonIds: string[]) => void;
  onRejectMany?: (lessonIds: string[]) => void;
  busyId: string | null;
  error: string | null;
}) {
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editedText, setEditedText] = React.useState("");
  const [previewId, setPreviewId] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<ReadonlySet<string>>(() => new Set());

  React.useEffect(() => {
    setSelected((prev) => {
      const ids = new Set(lessons.map((l) => l.id));
      const next = new Set<string>();
      for (const id of prev) {
        if (ids.has(id)) next.add(id);
      }
      return next.size === prev.size ? prev : next;
    });
  }, [lessons]);

  const allSelected = lessons.length > 0 && selected.size === lessons.length;
  const busy = busyId !== null;

  function startEdit(lesson: Lesson) {
    setEditingId(lesson.id);
    setEditedText(lesson.generalizable_rule);
    setPreviewId(lesson.id);
  }

  function saveEdit(lessonId: string) {
    onAccept(lessonId, editedText);
    setEditingId(null);
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(lessons.map((l) => l.id)));
  }

  function ruleFor(lesson: Lesson): string {
    return editingId === lesson.id ? editedText : lesson.generalizable_rule;
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-card p-4">
      <h2 className="font-serif text-lg font-semibold">Proposed lessons</h2>
      <p className="text-sm text-muted-foreground">
        The machine <b className="text-foreground">proposes</b> lessons by diffing final vs.
        published; a human accepts/edits/rejects in one click, or in a batch.{" "}
        <b className="text-foreground">The machine never self-commits a brain change</b>. Accepted
        lessons commit to this voice&rsquo;s <code className="text-xs">content-lessons.md</code>.
      </p>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {lessons.length === 0 ? (
        <p className="text-sm text-muted-foreground">No pending lessons for this voice right now.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                aria-label="Select all proposed lessons"
              />
              Select all
            </label>
            {selected.size > 0 ? (
              <>
                <Button
                  size="sm"
                  onClick={() => {
                    const ids = [...selected];
                    if (onAcceptMany) onAcceptMany(ids);
                    else ids.forEach((id) => onAccept(id));
                  }}
                  disabled={busy}
                >
                  Accept {selected.size} selected
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    const ids = [...selected];
                    if (onRejectMany) onRejectMany(ids);
                    else ids.forEach((id) => onReject(id));
                  }}
                  disabled={busy}
                >
                  Reject {selected.size} selected
                </Button>
              </>
            ) : null}
          </div>
          <ul className="flex flex-col gap-3">
            {lessons.map((lesson) => {
              const rule = ruleFor(lesson);
              const showingPreview = previewId === lesson.id;
              return (
                <li
                  key={lesson.id}
                  data-testid={`lesson-${lesson.id}`}
                  className="rounded-md border p-3"
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={selected.has(lesson.id)}
                      onChange={() => toggleOne(lesson.id)}
                      aria-label={`Select lesson: ${lesson.generalizable_rule}`}
                    />
                    <div className="min-w-0 flex-1">
                      {editingId === lesson.id ? (
                        <TextArea
                          aria-label="Edit lesson rule"
                          value={editedText}
                          onChange={(e) => setEditedText(e.target.value)}
                          rows={2}
                        />
                      ) : (
                        <p className="text-sm">{lesson.generalizable_rule}</p>
                      )}
                      {lesson.observed_change ? (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Observed: {lesson.observed_change}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex w-48 flex-wrap justify-end gap-1.5">
                      {editingId === lesson.id ? (
                        <>
                          <Button
                            size="sm"
                            onClick={() => saveEdit(lesson.id)}
                            disabled={busyId === lesson.id || busyId === "batch"}
                          >
                            Save & accept
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                            Cancel
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button
                            size="sm"
                            onClick={() => onAccept(lesson.id)}
                            disabled={busyId === lesson.id || busyId === "batch"}
                          >
                            Accept
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => startEdit(lesson)}>
                            Edit
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => onReject(lesson.id)}
                            disabled={busyId === lesson.id || busyId === "batch"}
                          >
                            Reject
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 pl-7">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setPreviewId(showingPreview ? null : lesson.id)}
                    >
                      {showingPreview ? "Hide Git preview" : "Preview Git change"}
                    </Button>
                    {showingPreview ? (
                      <div className="mt-2">
                        <p className="mb-1 text-xs text-muted-foreground">
                          What Accept will append to <code>content-lessons.md</code>
                        </p>
                        <DiffView before={currentLessonsFile} after={applyLessonRule(currentLessonsFile, rule)} />
                      </div>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}
      <p className="text-xs text-muted-foreground">
        Lessons are per-voice — one voice&rsquo;s edits teach that voice&rsquo;s file, never another&rsquo;s.
      </p>
    </div>
  );
}
