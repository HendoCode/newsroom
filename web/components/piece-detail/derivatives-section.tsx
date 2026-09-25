import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { phaseLabel } from "@/lib/content-workflow/labels";
import {
  COMMISSION_CHILD_REASON,
  COMMISSION_NOT_BUILT_REASON,
  DERIVATIVE_QUALITY_BAR,
  derivativeCouncilEditors,
  derivativeSlots,
  lineageOf,
  promotedHref,
  type DerivativeQuality,
  type ExistingDerivative,
} from "@/lib/pieces/derivatives";

/**
 * Target-IA Derivatives surface (cmw-repurposing-derivatives-ia + cmw-lesson-lineage-impl +
 * cmw-derivative-quality-bar-impl).
 *
 * Child artifacts of the anchor by default. Promoted to a top-level piece only when a
 * derivative needs its own owner/review/publish state. Commission records the child (native
 * generation is still out of scope) when `onCommission` is provided; otherwise the button
 * stays disabled with an honest reason.
 *
 * Every publishable native derivative must clear ITS OWN council at {DERIVATIVE_QUALITY_BAR}/10
 * with destination-specific editors plus the universal facts/safety hard gates — surfaced here
 * per derivative from `quality`.
 */

function councilCaption(quality: DerivativeQuality | undefined, destination: string): string {
  const editors = quality?.editors?.length ? quality.editors : derivativeCouncilEditors(destination);
  const gates = quality?.universal_gates?.length ? quality.universal_gates : ["facts", "safety"];
  return `Own council ≥ ${DERIVATIVE_QUALITY_BAR}/10 · judges: ${editors.join(", ")} · universal gates: ${gates.join(", ")}`;
}

function QualityBadges({ quality }: { quality: DerivativeQuality | undefined }) {
  if (!quality) return null;
  if (quality.cleared) {
    return (
      <Badge variant="secondary">
        Council {quality.aggregate != null ? `${quality.aggregate}/10` : "cleared"}
      </Badge>
    );
  }
  const firstReason = quality.reasons[0];
  return (
    <Badge variant="warning" title={firstReason ?? undefined}>
      Council: not cleared
    </Badge>
  );
}

export function DerivativesSection({
  existing = [],
  onCommission,
  onPromote,
  busyId = null,
  error = null,
}: {
  existing?: readonly ExistingDerivative[];
  onCommission?: (destination: string) => void;
  onPromote?: (artifactId: string) => void;
  busyId?: string | null;
  error?: string | null;
}) {
  const slots = derivativeSlots(existing);
  const existingSlots = slots.filter((s) => s.kind === "existing");
  const creatableSlots = slots.filter((s) => s.kind === "creatable");
  const canCommission = typeof onCommission === "function";

  return (
    <Card id="derivatives">
      <CardHeader>
        <CardTitle className="text-lg">Derivatives</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          Publish is not the last beat. One main piece becomes native formats — LinkedIn, X, a
          newsletter — each a <b className="font-medium text-foreground">child of this piece</b>{" "}
          until it needs its own owner, review, or publish, then you promote it to its own piece.
          Every publishable native must clear <b className="font-medium text-foreground">its own
          council at {DERIVATIVE_QUALITY_BAR}/10</b> — destination-specific judges, plus the
          universal facts and safety gates — before it can ship. Native generation is not built
          yet; commissioning records the child.
        </p>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        <section className="flex flex-col gap-2" aria-labelledby="derivatives-existing">
          <h3 id="derivatives-existing" className="text-sm font-medium">
            Existing
            <span className="ml-2 font-normal text-muted-foreground">
              {existingSlots.length === 0
                ? "none commissioned yet"
                : `${existingSlots.length} native${existingSlots.length === 1 ? "" : "s"}`}
            </span>
          </h3>
          {existingSlots.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No derivative artifacts yet. The formats below are what this piece can become —
              children of this piece, not separate pieces, until you promote one.
            </p>
          ) : (
            <div className="flex flex-col divide-y rounded-md border">
              {existingSlots.map((slot) => {
                if (slot.kind !== "existing") return null;
                const label = slot.format?.label ?? slot.derivative.destination;
                const lineage = lineageOf(slot.derivative);
                const href = promotedHref(slot.derivative);
                const quality = slot.derivative.quality;
                const body = (
                  <div className="flex items-start justify-between gap-3 px-3 py-2 text-sm">
                    <div className="min-w-0">
                      <div className="font-medium text-foreground">{label}</div>
                      <div className="text-muted-foreground">{slot.derivative.title}</div>
                      <p className="text-xs text-muted-foreground">
                        {councilCaption(quality, slot.derivative.destination)}
                      </p>
                      {quality && !quality.cleared && quality.reasons[0] ? (
                        <p className="text-xs text-warning">{quality.reasons[0]}</p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
                      {lineage === "promoted" ? (
                        <Badge variant="secondary">Own piece</Badge>
                      ) : (
                        <Badge variant="muted">Child of this piece</Badge>
                      )}
                      <QualityBadges quality={quality} />
                      {slot.derivative.phase ? (
                        <Badge variant="muted">{phaseLabel(slot.derivative.phase)}</Badge>
                      ) : null}
                      {lineage === "child" && onPromote ? (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyId === slot.derivative.id}
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            onPromote(slot.derivative.id);
                          }}
                          aria-label={`Promote ${label} to its own piece`}
                        >
                          Promote
                        </Button>
                      ) : null}
                    </div>
                  </div>
                );
                return href ? (
                  <a
                    key={slot.derivative.id}
                    href={href}
                    className="block hover:bg-muted/40"
                  >
                    {body}
                  </a>
                ) : (
                  <div key={slot.derivative.id}>{body}</div>
                );
              })}
            </div>
          )}
        </section>

        <section className="flex flex-col gap-2" aria-labelledby="derivatives-creatable">
          <h3 id="derivatives-creatable" className="text-sm font-medium">
            Creatable
            <span className="ml-2 font-normal text-muted-foreground">
              {creatableSlots.length} format{creatableSlots.length === 1 ? "" : "s"}
            </span>
          </h3>
          <div className="flex flex-col divide-y rounded-md border">
            {creatableSlots.map((slot) => {
              if (slot.kind !== "creatable") return null;
              return (
                <div
                  key={slot.format.id}
                  className="flex items-start justify-between gap-3 px-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <div className="font-medium text-foreground">{slot.format.label}</div>
                    <p className="text-muted-foreground">{slot.format.blurb}</p>
                    <p className="text-xs text-muted-foreground">
                      {councilCaption(undefined, slot.format.id)}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!canCommission || busyId === slot.format.id}
                    title={canCommission ? COMMISSION_CHILD_REASON : COMMISSION_NOT_BUILT_REASON}
                    aria-label={
                      canCommission
                        ? `Commission ${slot.format.label}`
                        : `Commission ${slot.format.label} (not built yet)`
                    }
                    onClick={() => onCommission?.(slot.format.id)}
                  >
                    Commission
                  </Button>
                </div>
              );
            })}
          </div>
          <p className="text-xs text-muted-foreground">
            {canCommission ? COMMISSION_CHILD_REASON : COMMISSION_NOT_BUILT_REASON}
          </p>
        </section>
      </CardContent>
    </Card>
  );
}
