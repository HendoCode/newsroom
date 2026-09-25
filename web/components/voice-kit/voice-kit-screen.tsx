"use client";

import * as React from "react";

import { BrainVersionBadge } from "@/components/voice-kit/brain-version-badge";
import { CourtesyNote } from "@/components/voice-kit/courtesy-note";
import { EditorPane } from "@/components/voice-kit/editor-pane";
import { FileList } from "@/components/voice-kit/file-list";
import { LessonsGate } from "@/components/voice-kit/lessons-gate";
import { VersionHistory } from "@/components/voice-kit/version-history";
import { VoiceSelector } from "@/components/voice-kit/voice-selector";
import type { BrainStatus } from "@/lib/agents-client";
import type { AppUser } from "@/lib/session";
import { isOwnVoice } from "@/lib/voice-kit/is-own-voice";
import {
  VOICE_FILE_LABELS,
  type Lesson,
  type VoiceCommit,
  type VoiceFileKey,
  type VoicePack,
} from "@/lib/voice-kit/types";

function emptyPack(slug: string): VoicePack {
  return {
    slug,
    voice_guide: null,
    style_guide: null,
    content_lessons: null,
    visual_identity: null,
    brand_guidelines: null,
  };
}

/**
 * The voice-kit screen (cmw-ui-wireframes screen 11; D12): voice selector, pack file list, the
 * markdown view/edit/commit/diff pane, Git version history + rollback, and the per-voice
 * proposed-lessons accept/edit/reject gate. Everything reads/writes through the BFF proxy routes
 * under `/api/voices/*` and `/api/lessons/*` — this component holds only UI/orchestration state.
 */
export function VoiceKitScreen({
  user,
  initialVoices,
  initialVoice,
  initialPack,
  initialHistory,
  initialLessons,
  brainStatus,
}: {
  user: AppUser;
  initialVoices: string[];
  initialVoice: string;
  initialPack: VoicePack;
  initialHistory: VoiceCommit[];
  initialLessons: Lesson[];
  brainStatus: BrainStatus | null;
}) {
  const [voices] = React.useState(initialVoices);
  const [selectedVoice, setSelectedVoice] = React.useState(initialVoice);
  const [pack, setPack] = React.useState(initialPack);
  const [selectedFile, setSelectedFile] = React.useState<VoiceFileKey>("voice_guide");

  const [history, setHistory] = React.useState<VoiceCommit[]>(initialHistory);
  const [historyLoading, setHistoryLoading] = React.useState(false);
  const [rollingBack, setRollingBack] = React.useState(false);

  const [lessons, setLessons] = React.useState<Lesson[]>(initialLessons);
  const [lessonsBusyId, setLessonsBusyId] = React.useState<string | null>(null);
  const [lessonsError, setLessonsError] = React.useState<string | null>(null);

  const [committing, setCommitting] = React.useState(false);
  const [commitError, setCommitError] = React.useState<string | null>(null);

  async function loadHistory(voice: string, fileKey: VoiceFileKey) {
    setHistoryLoading(true);
    try {
      const res = await fetch(`/api/voices/${encodeURIComponent(voice)}/files/${fileKey}/history`, {
        cache: "no-store",
      });
      setHistory(res.ok ? ((await res.json()) as { commits: VoiceCommit[] }).commits : []);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function refetchPack(voice: string) {
    const res = await fetch(`/api/voices/${encodeURIComponent(voice)}`, { cache: "no-store" });
    setPack(res.ok ? await res.json() : emptyPack(voice));
  }

  async function handleSelectVoice(voice: string) {
    setSelectedVoice(voice);
    setSelectedFile("voice_guide");
    setCommitError(null);
    setLessonsError(null);
    const lessonsRes = await fetch(`/api/lessons/pending?voice=${encodeURIComponent(voice)}`, {
      cache: "no-store",
    });
    setLessons(lessonsRes.ok ? await lessonsRes.json() : []);
    await Promise.all([refetchPack(voice), loadHistory(voice, "voice_guide")]);
  }

  function handleSelectFile(fileKey: VoiceFileKey) {
    setSelectedFile(fileKey);
    setCommitError(null);
    void loadHistory(selectedVoice, fileKey);
  }

  async function handleCommit(content: string, message: string): Promise<boolean> {
    setCommitting(true);
    setCommitError(null);
    try {
      const res = await fetch(`/api/voices/${encodeURIComponent(selectedVoice)}/files/${selectedFile}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content, message }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ error: "commit failed" }));
        setCommitError("error" in body ? body.error : "commit failed");
        return false;
      }
      setPack((prev) => ({ ...prev, [selectedFile]: content }));
      await loadHistory(selectedVoice, selectedFile);
      return true;
    } catch (err) {
      setCommitError(err instanceof Error ? err.message : "commit failed");
      return false;
    } finally {
      setCommitting(false);
    }
  }

  async function fetchContentAt(sha: string): Promise<string> {
    const res = await fetch(
      `/api/voices/${encodeURIComponent(selectedVoice)}/files/${selectedFile}/at/${encodeURIComponent(sha)}`,
      { cache: "no-store" },
    );
    if (!res.ok) return "";
    return ((await res.json()) as { content: string }).content;
  }

  async function handleRollback(sha: string) {
    setRollingBack(true);
    try {
      const res = await fetch(
        `/api/voices/${encodeURIComponent(selectedVoice)}/files/${selectedFile}/rollback`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ sha }),
        },
      );
      if (!res.ok) return;
      await Promise.all([refetchPack(selectedVoice), loadHistory(selectedVoice, selectedFile)]);
    } finally {
      setRollingBack(false);
    }
  }

  async function handleAcceptLesson(lessonId: string, ruleText?: string) {
    setLessonsBusyId(lessonId);
    setLessonsError(null);
    try {
      const res = await fetch(`/api/lessons/${encodeURIComponent(lessonId)}/accept`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(ruleText ? { rule_text: ruleText } : {}),
      });
      if (!res.ok) {
        setLessonsError("accept failed");
        return;
      }
      setLessons((prev) => prev.filter((l) => l.id !== lessonId));
      // An accepted lesson always commits to this voice's content-lessons.md (D12) — refresh
      // both the pack (whichever file is showing) and that file's history so it's reflected.
      await Promise.all([refetchPack(selectedVoice), loadHistory(selectedVoice, "content_lessons")]);
    } finally {
      setLessonsBusyId(null);
    }
  }

  async function handleRejectLesson(lessonId: string) {
    setLessonsBusyId(lessonId);
    setLessonsError(null);
    try {
      const res = await fetch(`/api/lessons/${encodeURIComponent(lessonId)}/reject`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        setLessonsError("reject failed");
        return;
      }
      setLessons((prev) => prev.filter((l) => l.id !== lessonId));
    } finally {
      setLessonsBusyId(null);
    }
  }

  async function handleAcceptMany(lessonIds: string[]) {
    setLessonsBusyId("batch");
    setLessonsError(null);
    try {
      const res = await fetch("/api/lessons/batch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "accept", lesson_ids: lessonIds }),
      });
      if (!res.ok) {
        setLessonsError("accept failed");
        return;
      }
      const body = (await res.json()) as { decided: { id: string }[]; errors: { id: string; error: string }[] };
      const decided = new Set(body.decided.map((item) => item.id));
      setLessons((prev) => prev.filter((l) => !decided.has(l.id)));
      if (body.errors.length > 0) {
        setLessonsError(`accept failed for ${body.errors.length} lesson${body.errors.length === 1 ? "" : "s"}`);
      }
      await Promise.all([refetchPack(selectedVoice), loadHistory(selectedVoice, "content_lessons")]);
    } finally {
      setLessonsBusyId(null);
    }
  }

  async function handleRejectMany(lessonIds: string[]) {
    setLessonsBusyId("batch");
    setLessonsError(null);
    try {
      const res = await fetch("/api/lessons/batch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "reject", lesson_ids: lessonIds }),
      });
      if (!res.ok) {
        setLessonsError("reject failed");
        return;
      }
      const body = (await res.json()) as { decided: { id: string }[]; errors: { id: string; error: string }[] };
      const decided = new Set(body.decided.map((item) => item.id));
      setLessons((prev) => prev.filter((l) => !decided.has(l.id)));
      if (body.errors.length > 0) {
        setLessonsError(`reject failed for ${body.errors.length} lesson${body.errors.length === 1 ? "" : "s"}`);
      }
    } finally {
      setLessonsBusyId(null);
    }
  }

  const currentContent = pack[selectedFile] ?? "";

  return (
    <section className="flex flex-col gap-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-serif text-3xl font-semibold">Voice kits</h1>
          <BrainVersionBadge status={brainStatus} />
        </div>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Voice packs are markdown, versioned in Git — history, diff, and rollback come for free
          (D2). Any employee can edit any kit; there is no approval workflow (D12).
        </p>
      </div>

      <VoiceSelector voices={voices} selected={selectedVoice} onSelect={handleSelectVoice} />

      {!isOwnVoice(selectedVoice, user) ? <CourtesyNote voice={selectedVoice} /> : null}

      <div className="grid gap-4 lg:grid-cols-[200px_1fr_320px]">
        <FileList
          slug={selectedVoice}
          pack={pack}
          selected={selectedFile}
          onSelect={handleSelectFile}
          pendingLessonCount={lessons.length}
        />

        <div className="flex flex-col gap-4">
          <EditorPane
            key={`${selectedVoice}-${selectedFile}`}
            fileLabel={VOICE_FILE_LABELS[selectedFile]}
            content={currentContent}
            onCommit={handleCommit}
            committing={committing}
            commitError={commitError}
          />
          <LessonsGate
            lessons={lessons}
            currentLessonsFile={pack.content_lessons ?? ""}
            onAccept={handleAcceptLesson}
            onReject={handleRejectLesson}
            onAcceptMany={handleAcceptMany}
            onRejectMany={handleRejectMany}
            busyId={lessonsBusyId}
            error={lessonsError}
          />
        </div>

        <VersionHistory
          commits={history}
          currentContent={currentContent}
          fetchContentAt={fetchContentAt}
          onRollback={handleRollback}
          rollingBack={rollingBack}
          loading={historyLoading}
        />
      </div>
    </section>
  );
}
