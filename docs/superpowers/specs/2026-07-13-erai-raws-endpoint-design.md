# Erai-raws endpoint (tokenized RSS) design

Date: 2026-07-13. Status: approved by Marcus (interactive session).

## Goal

Add Erai-raws' members-only tokenized RSS as a search + subscription source,
using their per-show feeds for precise qBittorrent subscriptions.

## Feed facts (verified live 2026-07-13)

- Search: `https://www.erai-raws.info/episodes/feed/?res=1080p&type=torrent&subs[0]=us&s=<terms>&token=<token>`.
  WordPress `s=` search: multi-word is AND, `res`/`type`/`subs` filters stay
  active, the path section (episodes/batches/...) is ignored under `s=`, so a
  search covers all sections. Searches reach months of history.
- Per-show: `https://www.erai-raws.info/anime-list/<slug>/feed/?res=...&type=...&subs[0]=us&token=...`.
  Contains only the show's current offerings: recent episodes plus HEVC
  re-encodes while airing, only the batch once finished. Without `res`/`type`
  it mixes every resolution and Torrent+Magnet duplicates, so params must
  always be carried. A wrong slug returns HTTP 200 with an empty feed (never
  an error page).
- Items carry an `erai:` namespace (resolution, size, infohash, subtitles,
  category, linktype) and a `<description>` linking the post URL:
  `episodes/<slug>-02/`, `encodes/<slug>-01-hevc/`, `batches/<slug>-01-11/`.
  The show slug is derivable by stripping the trailing suffix per section.
- Raw titles: `[Torrent] Show - 02 [1080p CR WEB-DL AVC AAC][us][br]...[Airing]`.
  No release-group poster, no seeder/leecher/download stats. Batch titles
  carry no codec info; encodes say HEVC.

## Design

1. Search transport: existing `rss` endpoint kind, zero new plumbing. The
   config URL embeds `s={query}` and the token. Endpoint priority: erai
   first, nyaa second (Marcus's choice).
2. Parser (nyaa.py): when an item has `erai:linktype`, treat it as an
   Erai-raws item: strip the `[Torrent]`/`[Magnet]` title prefix, remove the
   `erai:subtitles` language run from the title (keeping `[Airing]`/
   `[Encoded]`/`[Batch]` as a refine facet), take size/category from
   `erai:size`/`erai:category`, and record the post URL from the description
   into a new `Item.page` field (default "", harmless elsewhere).
3. Subscribe (new `erai.py` + `endpoints.subscription_feed()`): for erai
   endpoints, derive the show slug from the first item with a post URL
   (episodes: strip `-NN`; encodes: strip `-hevc` then `-NN`; batches: strip
   `-NN-NN`), build the anime-list feed URL carrying over `res`/`type`/
   `subs`/`token` (dropping `s`), and validate it with one fetch. Non-empty
   means subscribe to it, with the qB rule's `mustContain` set to the
   positive query terms (quotes stripped, bracketed poster fields dropped).
   That pins the variant: batch and HEVC titles fail a `WEB-DL AVC` match,
   so season-end batches never re-download. Empty feed, no post URL, or a
   fetch error falls back to today's behavior (search-feed URL, empty
   mustContain). `do_subscribe()` gains a `must_contain` parameter.
4. Rate limits: search behaves like nyaa (one request per query/refine
   step); subscribing adds exactly one validation request. Nothing polls.

## Out of scope

Slug lookup by scraping the anime-list index, config keys for res/subs
(the URL in config already carries them), non-us subtitle handling.
