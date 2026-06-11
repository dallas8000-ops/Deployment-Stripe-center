interface CompletionData {
  score: number | null;
  filesGenerated: string[];
  productsProvisioned: number;
  pricesProvisioned: number;
  webhookRegistered: boolean;
  nextSteps: string[];
}

interface Props {
  data: CompletionData;
  runId: string | null;
  hasLocalPath: boolean;
  onOpenPr: () => void;
  onDownload: () => void;
  downloading: boolean;
  openingPr: boolean;
}

function scoreBadgeClass(score: number | null): string {
  if (score == null) return "score-badge-muted";
  if (score >= 90) return "score-badge-green";
  if (score >= 70) return "score-badge-brand";
  if (score >= 50) return "score-badge-yellow";
  return "score-badge-red";
}

export type { CompletionData };

export default function PipelineCompleteCard({
  data,
  runId,
  hasLocalPath,
  onOpenPr,
  onDownload,
  downloading,
  openingPr,
}: Props) {
  const { score, filesGenerated, productsProvisioned, pricesProvisioned, webhookRegistered, nextSteps } = data;

  return (
    <div className="pipeline-complete-card">
      {/* Header */}
      <div className="pcc-header">
        <span className="pcc-check">✓</span>
        <span className="pcc-title">Setup complete</span>
        {score != null && (
          <span className={`pcc-score-badge ${scoreBadgeClass(score)}`}>
            Score {score}
          </span>
        )}
      </div>

      <div className="pcc-body">
        {/* Generated files */}
        {filesGenerated.length > 0 && (
          <div className="pcc-row">
            <span className="pcc-label">Generated</span>
            <div className="pcc-files">
              {filesGenerated.map((f) => (
                <code key={f} className="pcc-file-pill">{f}</code>
              ))}
            </div>
          </div>
        )}

        {/* Provisioned */}
        {(productsProvisioned > 0 || pricesProvisioned > 0) && (
          <div className="pcc-row">
            <span className="pcc-label">Provisioned</span>
            <div className="pcc-provision-list">
              {productsProvisioned > 0 && (
                <span className="pcc-provision-item">
                  {productsProvisioned} Stripe product{productsProvisioned !== 1 ? "s" : ""}
                </span>
              )}
              {pricesProvisioned > 0 && (
                <span className="pcc-provision-item">
                  {pricesProvisioned} price{pricesProvisioned !== 1 ? "s" : ""}
                </span>
              )}
              {webhookRegistered && (
                <span className="pcc-provision-item pcc-provision-badge">webhook registered</span>
              )}
            </div>
          </div>
        )}

        {/* Next step */}
        <div className="pcc-next">
          <span className="pcc-arrow">→</span>
          <span>
            {nextSteps.length > 0
              ? nextSteps[0]
              : "Merge the generated code into your repo to go live"}
          </span>
        </div>
      </div>

      {/* Actions */}
      <div className="pcc-actions">
        {hasLocalPath && (
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={onOpenPr}
            disabled={openingPr}
          >
            {openingPr ? "Opening…" : "Open GitHub PR"}
          </button>
        )}
        {runId && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onDownload}
            disabled={downloading}
          >
            {downloading ? "…" : "Download zip"}
          </button>
        )}
      </div>
    </div>
  );
}
