import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VoiceKitScreen } from "@/components/voice-kit/voice-kit-screen";
import type { AppUser } from "@/lib/session";
import type { Lesson, VoiceCommit, VoicePack } from "@/lib/voice-kit/types";

const USER: AppUser = { email: "demo-mira@example.com", name: "Demo-mira H", image: null };

const PACK: VoicePack = {
  slug: "demo-mira",
  voice_guide: "# Voice — Demo-mira\nOriginal register.",
  style_guide: "# Style",
  content_lessons: "- an existing lesson",
  visual_identity: null,
  brand_guidelines: null,
};

const HISTORY: VoiceCommit[] = [
  {
    sha: "aaaaaaaaaaaa",
    author_name: "Demo-mira",
    author_email: "demo-mira@example.com",
    date: "2026-07-20T00:00:00.000Z",
    message: "initial pack",
  },
];

const LESSON: Lesson = {
  id: "lesson-1",
  voice: "demo-mira",
  source_piece_id: "piece-1",
  observed_change: "cut the caveat",
  generalizable_rule: "Say “field extraction,” not just “extraction.”",
  status: "proposed",
};

function renderScreen(opts: { lessons?: Lesson[]; user?: AppUser; voice?: string } = {}) {
  return render(
    <VoiceKitScreen
      user={opts.user ?? USER}
      initialVoices={["demo-alex", "demo-mira", "demo-dana"]}
      initialVoice={opts.voice ?? "demo-mira"}
      initialPack={PACK}
      initialHistory={HISTORY}
      initialLessons={opts.lessons ?? []}
      brainStatus={null}
    />,
  );
}

function editorHeaderScope(fileLabel: string) {
  return within(screen.getByRole("heading", { name: fileLabel }).closest("div") as HTMLElement);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("VoiceKitScreen — edit/commit flow", () => {
  it("Commit change PUTs the edited content + message to /api/voices/:slug/files/:fileKey", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url === "/api/voices/demo-mira/files/voice_guide" && options?.method === "PUT") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            sha: "bbbbbbbbbbbb",
            author_name: "Demo-mira",
            author_email: "demo-mira@example.com",
            date: "2026-07-30T00:00:00.000Z",
            message: "tighten register",
          }),
        });
      }
      if (url === "/api/voices/demo-mira/files/voice_guide/history") {
        return Promise.resolve({ ok: true, json: async () => ({ commits: HISTORY }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderScreen();

    fireEvent.click(editorHeaderScope("voice-guide.md").getByRole("button", { name: "Edit" }));
    const textarea = screen.getByLabelText("Edit voice-guide.md");
    fireEvent.change(textarea, { target: { value: "# Voice — Demo-mira\nA tighter register." } });
    fireEvent.change(screen.getByLabelText("Commit message"), { target: { value: "tighten register" } });

    fireEvent.click(screen.getByRole("button", { name: "Commit change" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/voices/demo-mira/files/voice_guide",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    const call = fetchMock.mock.calls.find(
      (c: unknown[]) => c[0] === "/api/voices/demo-mira/files/voice_guide",
    )!;
    const options = call[1] as RequestInit & { body: string };
    expect(JSON.parse(options.body)).toEqual({
      content: "# Voice — Demo-mira\nA tighter register.",
      message: "tighten register",
    });

    // Returns to view mode showing the newly-committed content.
    await waitFor(() => expect(screen.queryByLabelText("Edit voice-guide.md")).not.toBeInTheDocument());
    expect(screen.getByText(/A tighter register/)).toBeInTheDocument();
  });

  it("Diff vs current shows the pending edit as added lines before committing", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderScreen();

    fireEvent.click(editorHeaderScope("voice-guide.md").getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Edit voice-guide.md"), {
      target: { value: "# Voice — Demo-mira\nOriginal register.\nA brand new line." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Diff vs current" }));

    expect(within(screen.getByTestId("diff-view")).getByText(/A brand new line\./)).toBeInTheDocument();
  });

  it("Cancel discards the draft and returns to view mode without committing", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderScreen();

    fireEvent.click(editorHeaderScope("voice-guide.md").getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Edit voice-guide.md"), { target: { value: "throwaway edit" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Edit voice-guide.md")).not.toBeInTheDocument();
    expect(screen.getByText(/Original register\./)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("surfaces the server error and stays in edit mode when the commit fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ error: "no staged changes" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderScreen();

    fireEvent.click(editorHeaderScope("voice-guide.md").getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Edit voice-guide.md"), { target: { value: "a change" } });
    fireEvent.click(screen.getByRole("button", { name: "Commit change" }));

    await screen.findByText("no staged changes");
    expect(screen.getByLabelText("Edit voice-guide.md")).toBeInTheDocument();
  });
});

describe("VoiceKitScreen — proposed-lessons accept/edit/reject gate", () => {
  it("Accept posts to /api/lessons/:id/accept with no body override and removes the row", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url === "/api/lessons/lesson-1/accept" && options?.method === "POST") {
        return Promise.resolve({ ok: true, json: async () => ({ ...LESSON, status: "accepted" }) });
      }
      if (url === "/api/voices/demo-mira") {
        return Promise.resolve({ ok: true, json: async () => PACK });
      }
      if (url === "/api/voices/demo-mira/files/content_lessons/history") {
        return Promise.resolve({ ok: true, json: async () => ({ commits: HISTORY }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderScreen({ lessons: [LESSON] });
    const row = screen.getByTestId("lesson-lesson-1");

    fireEvent.click(within(row).getByRole("button", { name: "Accept" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/lessons/lesson-1/accept",
        expect.objectContaining({ method: "POST", body: "{}" }),
      ),
    );
    await waitFor(() => expect(screen.queryByText(LESSON.generalizable_rule)).not.toBeInTheDocument());
    expect(screen.getByText(/No pending lessons/)).toBeInTheDocument();
  });

  it("Edit then Save & accept sends the edited phrasing as rule_text (one-click accept-with-edit)", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/lessons/lesson-1/accept") {
        return Promise.resolve({ ok: true, json: async () => ({ ...LESSON, status: "accepted" }) });
      }
      if (url === "/api/voices/demo-mira") {
        return Promise.resolve({ ok: true, json: async () => PACK });
      }
      if (url === "/api/voices/demo-mira/files/content_lessons/history") {
        return Promise.resolve({ ok: true, json: async () => ({ commits: HISTORY }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderScreen({ lessons: [LESSON] });
    const row = screen.getByTestId("lesson-lesson-1");

    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Edit lesson rule"), {
      target: { value: "Say field extraction, always." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save & accept" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/lessons/lesson-1/accept",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const call = fetchMock.mock.calls.find((c: unknown[]) => c[0] === "/api/lessons/lesson-1/accept")!;
    const options = call[1] as RequestInit & { body: string };
    expect(JSON.parse(options.body)).toEqual({ rule_text: "Say field extraction, always." });
  });

  it("Reject posts to /api/lessons/:id/reject and removes the row without touching voice files", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url === "/api/lessons/lesson-1/reject" && options?.method === "POST") {
        return Promise.resolve({ ok: true, json: async () => ({ ...LESSON, status: "rejected" }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderScreen({ lessons: [LESSON] });
    const row = screen.getByTestId("lesson-lesson-1");

    fireEvent.click(within(row).getByRole("button", { name: "Reject" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/lessons/lesson-1/reject",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() => expect(screen.queryByText(LESSON.generalizable_rule)).not.toBeInTheDocument());
    // Reject never reaches Git — no voice-pack refetch should have happened.
    expect(fetchMock).not.toHaveBeenCalledWith("/api/voices/demo-mira", expect.anything());
  });

  it("shows an inline error and keeps the row when accept fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: "conflict" }) });
    vi.stubGlobal("fetch", fetchMock);

    renderScreen({ lessons: [LESSON] });
    const row = screen.getByTestId("lesson-lesson-1");
    fireEvent.click(within(row).getByRole("button", { name: "Accept" }));

    await screen.findByText("accept failed");
    expect(screen.getByText(LESSON.generalizable_rule)).toBeInTheDocument();
  });
});

describe("VoiceKitScreen — courtesy note (D12)", () => {
  it("shows the courtesy note when the signed-in user doesn't own the selected voice", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderScreen({ voice: "demo-alex", user: USER });

    expect(screen.getByText(/Courtesy note/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("demo-alex");
  });

  it("hides the courtesy note when editing your own voice", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderScreen({ voice: "demo-mira", user: USER });

    expect(screen.queryByText(/Courtesy note/)).not.toBeInTheDocument();
  });

  it("never shows the courtesy note for the shared team voice", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderScreen({ voice: "demo-dana", user: USER });

    expect(screen.queryByText(/Courtesy note/)).not.toBeInTheDocument();
  });
});

describe("VoiceKitScreen — voice switching", () => {
  it("switching voices refetches the pack, history, and pending lessons for the new voice", async () => {
    const danaPack: VoicePack = { ...PACK, slug: "demo-dana", voice_guide: "# Voice — Demo-dana" };
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/lessons/pending?voice=demo-dana") {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url === "/api/voices/demo-dana") {
        return Promise.resolve({ ok: true, json: async () => danaPack });
      }
      if (url === "/api/voices/demo-dana/files/voice_guide/history") {
        return Promise.resolve({ ok: true, json: async () => ({ commits: [] }) });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderScreen();
    fireEvent.click(screen.getByRole("tab", { name: "demo-dana" }));

    await screen.findByText("# Voice — Demo-dana");
    expect(fetchMock).toHaveBeenCalledWith("/api/lessons/pending?voice=demo-dana", expect.anything());
  });
});
