#!/usr/bin/env bash
# Single-call extraction across the non-BPHS corpus, one book at a time.
#
#   ./scripts/extract_all.sh            # resume: skips books already done
#   ./scripts/extract_all.sh --force    # start over
#
# Per book rather than one long run, for two reasons. `write_grouped` writes one
# file per domain and overwrites it, so a single invocation over twelve books
# would be fine but a crash six hours in loses everything; and a per-book output
# directory means the twelfth book cannot clobber the first. The compiler globs
# rules/ recursively, so `extracted/<book>/` is loaded without further wiring.
#
# Smallest books first. If something is wrong with the prompt or the registry it
# shows up in four minutes on Bhavartha Ratnakara rather than ninety on
# Sarvartha Chintamani.

set -uo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
OUT=rishivan/koonji/rules/extracted
STAGE=${STAGE:-.koonji-staging}
LOGS=logs
WORKERS=${WORKERS:-16}

BOOKS=(
  prasna-marga           # 37 passages
  bhavartha-ratnakara    # 7
  brihat-jataka          # 13
  phaladeepika           # 141
  jataka-parijata        # 687
  hindu-predictive       # 304
  prashna-tantra         # 339
  muhurta-chintamani     # 412
  saravali               # 557
  sarvartha-chintamani   # 1112
)

[ "${1:-}" = "--force" ] && rm -rf "$OUT" "$STAGE"
mkdir -p "$OUT" "$STAGE" "$LOGS"

for book in "${BOOKS[@]}"; do
  if [ -d "$OUT/$book" ] && [ -n "$(ls -A "$OUT/$book" 2>/dev/null)" ]; then
    echo "== $book already extracted, skipping"
    continue
  fi
  log="$LOGS/extract-$book-$(date +%Y%m%d-%H%M).log"
  echo "== $book  (workers=$WORKERS)  -> $log"

  # max-calls is a safety net, not a target: single-call mode spends one call
  # per passage, so a ceiling well above the passage count only catches a bug
  # that turns one call into a loop.
  # `--rules` is a GLOBAL argument and has to precede the subcommand. Behind
  # the subcommand argparse rejects it, the run exits before spending anything,
  # and the only symptom is "no rules written".
  # `--limit 0` means the whole book. The CLI default is 20 and deliberately
  # low, which is right for a proving run and wrong here -- without this every
  # book silently stops after twenty passages and reports success.
  $PY -m rishivan.koonji --rules "$STAGE/$book" extract \
      --book "$book" \
      --single-call \
      --limit 0 \
      --workers "$WORKERS" \
      --max-calls 4000 >"$log" 2>&1

  if [ -d "$STAGE/$book/extracted" ]; then
    mkdir -p "$OUT/$book"
    cp "$STAGE/$book/extracted/"*.yaml "$OUT/$book/" 2>/dev/null
    echo "   $(grep -h -o '^- id:' "$OUT/$book/"*.yaml 2>/dev/null | wc -l | tr -d ' ') rules -> $OUT/$book/"
  else
    echo "   no rules written; see $log"
  fi
  tail -4 "$log" | sed 's/^/   /'
done

echo
echo "== total rules on disk:"
echo "   $(grep -rh -o '^- id:' "$OUT" 2>/dev/null | wc -l | tr -d ' ')"
