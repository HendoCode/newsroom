"use client";

import { Button } from "@/components/ui/button";

/** The voice selector (cmw-ui-wireframes screen 11): demo-mira / demo-dana / demo-dana, and any other
 * voice pack the brain holds. Flat — any employee may select and edit any voice (D12). */
export function VoiceSelector({
  voices,
  selected,
  onSelect,
}: {
  voices: string[];
  selected: string;
  onSelect: (voice: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Voice">
      {voices.map((voice) => (
        <Button
          key={voice}
          type="button"
          variant={voice === selected ? "default" : "outline"}
          role="tab"
          aria-selected={voice === selected}
          onClick={() => onSelect(voice)}
          className="h-auto px-3 py-1.5"
        >
          {voice}
        </Button>
      ))}
    </div>
  );
}
