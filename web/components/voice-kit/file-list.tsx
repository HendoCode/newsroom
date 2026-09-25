"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  CORE_VOICE_FILES,
  TEAM_ONLY_VOICE_FILES,
  VOICE_FILE_LABELS,
  type VoiceFileKey,
  type VoicePack,
} from "@/lib/voice-kit/types";

/** The pack file list (cmw-ui-wireframes screen 11): voice-guide / style-guide / content-lessons
 * for every voice; visual-identity + brand-guidelines additionally for the team voice. The
 * content-lessons row carries a pending-lesson count pill. */
export function FileList({
  slug,
  pack,
  selected,
  onSelect,
  pendingLessonCount,
}: {
  slug: string;
  pack: VoicePack;
  selected: VoiceFileKey;
  onSelect: (fileKey: VoiceFileKey) => void;
  pendingLessonCount: number;
}) {
  const files = [
    ...CORE_VOICE_FILES,
    ...(slug === "demo-dana" ? TEAM_ONLY_VOICE_FILES : []),
  ];

  return (
    <div className="flex flex-col gap-1.5">
      <h3 className="text-sm font-semibold text-muted-foreground">{slug} pack</h3>
      {files.map((fileKey) => (
        <Button
          key={fileKey}
          type="button"
          variant="outline"
          aria-pressed={fileKey === selected}
          onClick={() => onSelect(fileKey)}
          disabled={pack[fileKey] === null}
          className={cn(
            "h-auto w-full justify-between px-3 py-2 text-left font-normal",
            fileKey === selected && "border-primary bg-primary/5 font-semibold",
          )}
        >
          <span>{VOICE_FILE_LABELS[fileKey]}</span>
          {fileKey === "content_lessons" && pendingLessonCount > 0 ? (
            <Badge variant="warning">{pendingLessonCount}</Badge>
          ) : null}
        </Button>
      ))}
    </div>
  );
}
