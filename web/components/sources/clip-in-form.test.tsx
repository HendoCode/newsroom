import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ClipInForm } from "@/components/sources/clip-in-form";

const NOW = new Date("2026-07-30T12:00:00.000Z");

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ClipInForm", () => {
  it("disables the form and explains why when no clip-in source exists yet", () => {
    render(<ClipInForm clipSourceId={null} now={NOW} />);
    expect(
      screen.getByText(/no linkedin \/ x clip-in source is set up yet/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Paste text or URL")).not.toBeInTheDocument();
  });

  it("offers a shortcut to set up the missing clip-in source", () => {
    const onSetupSource = vi.fn();
    render(<ClipInForm clipSourceId={null} now={NOW} onSetupSource={onSetupSource} />);
    fireEvent.click(screen.getByRole("button", { name: "Set up a clip-in source" }));
    expect(onSetupSource).toHaveBeenCalledTimes(1);
  });

  it("omits the setup shortcut when there's nowhere to jump to", () => {
    render(<ClipInForm clipSourceId={null} now={NOW} />);
    expect(screen.queryByRole("button", { name: "Set up a clip-in source" })).not.toBeInTheDocument();
  });

  it("submits pasted content + metadata to the clip-in endpoint and shows success", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: "item-1", classification: "read-as-needed", indexed: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ClipInForm clipSourceId="src-linkedin" now={NOW} />);

    fireEvent.change(screen.getByLabelText("Paste text or URL"), {
      target: { value: "A sharp take on storage economics." },
    });
    fireEvent.change(screen.getByLabelText("Source person / account"), {
      target: { value: "Jane Expert" },
    });
    fireEvent.change(screen.getByLabelText("Tags (optional)"), {
      target: { value: "genai, pricing" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Add clip to content lake" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const call = fetchMock.mock.calls[0];
    if (!call) throw new Error("fetch was not called");
    const [url, options] = call;
    expect(url).toBe("/api/connectors/clip");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body).toMatchObject({
      source_id: "src-linkedin",
      content: "A sharp take on storage economics.",
      author: "Jane Expert",
      content_date: "2026-07-30",
      tags: ["genai", "pricing"],
    });

    await screen.findByText("Clip added to the content lake.");
    // The form clears pasted content/author/tags after a successful clip.
    expect(screen.getByLabelText("Paste text or URL")).toHaveValue("");
  });

  it("surfaces the error message and keeps the input when the clip-in call fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ error: "clip-in requires a linkedin-x-clip source" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ClipInForm clipSourceId="src-linkedin" now={NOW} />);
    fireEvent.change(screen.getByLabelText("Paste text or URL"), {
      target: { value: "some text" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add clip to content lake" }));

    await screen.findByText("clip-in requires a linkedin-x-clip source");
    expect(screen.getByLabelText("Paste text or URL")).toHaveValue("some text");
  });
});
