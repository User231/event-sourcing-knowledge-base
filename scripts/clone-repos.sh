#!/usr/bin/env bash
# Clone (or update) the reference event sourcing repos under repos_cloned/.
# These are kept locally only — not committed — so Serena and Codegraph have
# real source to index without nesting git repositories inside this one.

set -euo pipefail

cd "$(dirname "$0")/.."

REPOS=(
  "EventStore/EventStore"
  "JasperFx/marten"
  "commanded/commanded"
  "AxonFramework/AxonFramework"
  "eventuous/eventuous"
  "thalo-rs/thalo"
  "eventsourcing/es4j"
  "prooph/event-store"
  "oskardudycz/EventSourcing.NetCore"
  "oskardudycz/EventSourcing.JVM"
  "oskardudycz/EventSourcing.NodeJS"
  "pyeventsourcing/eventsourcing"
  "castore-dev/castore"
  "ocoda/event-sourcing"
  "NickTsitlakidis/event-nest"
)

mkdir -p repos_cloned

for repo in "${REPOS[@]}"; do
  owner="${repo%%/*}"
  name="${repo##*/}"
  dest="repos_cloned/${owner}_${name}"

  if [[ -d "$dest/.git" ]]; then
    echo "==> Updating $repo"
    git -C "$dest" pull --ff-only --depth=1 || echo "    (pull failed; skipping)"
  else
    echo "==> Cloning $repo"
    git clone --depth=1 "https://github.com/${repo}.git" "$dest"
  fi
done

echo
echo "Done. After cloning, refresh indexes:"
echo "  codegraph index"
echo "  # Serena reindexes lazily on tool calls."
