#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="results/benchmark_summary/tritonpart_timing_aware_probe"
mkdir -p "$OUT_DIR"

report="$OUT_DIR/triton_part_design_probe_report.txt"
help_log="$OUT_DIR/triton_part_design_help.log"
status_csv="$OUT_DIR/triton_part_design_status.csv"

: > "$report"

log() {
  printf '%s\n' "$*" | tee -a "$report"
}

section() {
  log ""
  log "=== $* ==="
}

section "environment"
log "repo=$REPO_ROOT"
if command -v openroad >/dev/null 2>&1; then
  log "openroad=$(command -v openroad)"
else
  log "openroad=not found on PATH"
fi

section "OpenROAD version"
if command -v openroad >/dev/null 2>&1; then
  openroad -version 2>&1 | tee -a "$report" || true
else
  log "skip: openroad not found"
fi

section "command help"
if command -v openroad >/dev/null 2>&1; then
  help_tcl="$OUT_DIR/help_triton_part_design.tcl"
  cat > "$help_tcl" <<'TCL'
help triton_part_design
help triton_part_hypergraph
exit
TCL
  openroad "$help_tcl" > "$help_log" 2>&1 || true
  sed -n '1,220p' "$help_log" | tee -a "$report"
else
  log "skip: openroad not found"
fi

design_present=false
timing_option_present=false
hypergraph_present=false

if [[ -f "$help_log" ]]; then
  if grep -q "triton_part_design" "$help_log" && ! grep -q "no commands match 'triton_part_design'" "$help_log"; then
    design_present=true
  fi
  if grep -q "triton_part_hypergraph" "$help_log" && ! grep -q "no commands match 'triton_part_hypergraph'" "$help_log"; then
    hypergraph_present=true
  fi
  if grep -qiE "timing_aware|extra_delay|guardband|top_n|path_timing|snaking|timing_exp" "$help_log"; then
    timing_option_present=true
  fi
fi

section "status"
log "triton_part_design_present=$design_present"
log "triton_part_hypergraph_present=$hypergraph_present"
log "timing_option_present=$timing_option_present"

{
  printf 'metric,value\n'
  printf 'triton_part_design_present,%s\n' "$design_present"
  printf 'triton_part_hypergraph_present,%s\n' "$hypergraph_present"
  printf 'timing_option_present,%s\n' "$timing_option_present"
  printf 'help_log,%s\n' "$help_log"
  printf 'probe_report,%s\n' "$report"
} > "$status_csv"

section "outputs"
log "$status_csv"
log "$help_log"
log "$report"
