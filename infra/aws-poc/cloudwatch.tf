# CloudWatch dashboard for Bedrock GLM inference cost (non-technical viewer audience).
# The app already computes truthful per-call cost_usd from AWS Price List rates (pricing.py)
# and attributes by pipeline step; Bedrock itself exposes no per-invocation USD cost for
# third-party models. So we emit the app's own number as a custom metric (InferenceCostUSD in
# Newsroom/Bedrock namespace, dimensions Step + Model) and surface it here.
#
# Dashboard shows: total spend, spend-by-step, invocation volume, average cost per call.
# Research sidecar is deliberately excluded (stays on direct Anthropic per captain carve-out);
# the title and description label this so the number is never mistaken for "total LLM spend".
# Emission is controllable via Settings.emit_bedrock_cost_metrics (default True for v1 launch).
#
# Cost: 1 custom metric (low cardinality) + 1 dashboard. Real figures: first 10 metrics free
# (not 10k as the research report loosely stated), first 3 dashboards free, then $0.30/metric/mo
# + $3/dashboard/mo. Still comfortably under $5/mo even at moderate volume.

resource "aws_cloudwatch_dashboard" "newsroom_bedrock_cost" {
  dashboard_name = "Newsroom-Bedrock-Cost"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 2
        properties = {
          markdown = "## Newsroom Bedrock GLM Cost Dashboard\n\n**Excludes research sidecar** (Anthropic direct per standing carve-out). Numbers reflect only Bedrock GLM5 inference (the live default for all pipeline steps). Per-call cost is the app's own truthful computation from AWS Price List rates."
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 2
        width  = 12
        height = 6
        properties = {
          metrics  = [["Newsroom/Bedrock", "InferenceCostUSD", { "stat" : "Sum", "label" : "Total USD" }]]
          period   = 3600
          stat     = "Sum"
          region   = "us-east-1"
          title    = "Total Bedrock Inference Spend (USD)"
          view     = "timeSeries"
          stacked  = false
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 2
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "oracle", { "stat" : "Sum" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "interview_question", { "stat" : "Sum" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "interview_classify", { "stat" : "Sum" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "recap", { "stat" : "Sum" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "draft", { "stat" : "Sum" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "council", { "stat" : "Sum" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "feedback_classify", { "stat" : "Sum" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "rewrite", { "stat" : "Sum" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "lessons", { "stat" : "Sum" }],
          ]
          period  = 3600
          stat    = "Sum"
          region  = "us-east-1"
          title   = "Spend by Pipeline Step (USD)"
          view    = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 8
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "oracle", { "stat" : "SampleCount" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "interview_question", { "stat" : "SampleCount" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "interview_classify", { "stat" : "SampleCount" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "recap", { "stat" : "SampleCount" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "draft", { "stat" : "SampleCount" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "council", { "stat" : "SampleCount" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "feedback_classify", { "stat" : "SampleCount" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "rewrite", { "stat" : "SampleCount" }],
            ["Newsroom/Bedrock", "InferenceCostUSD", "Step", "lessons", { "stat" : "SampleCount" }],
          ]
          period  = 3600
          stat    = "Sum"
          region  = "us-east-1"
          title   = "Invocations by Pipeline Step"
          view    = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 8
        width  = 12
        height = 6
        properties = {
          metrics  = [["Newsroom/Bedrock", "InferenceCostUSD", { "stat" : "Average", "label" : "Avg Cost per Call (USD)" }]]
          period   = 3600
          stat     = "Average"
          region   = "us-east-1"
          title    = "Average Cost per Inference Call (USD)"
          view     = "timeSeries"
        }
      },
    ]
  })
}
