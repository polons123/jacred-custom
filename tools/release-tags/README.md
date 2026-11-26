# Release title metadata

JacRed returns release-level claims in `Results[].info.releaseTags`. Each group of records with the same complete title shares a parser result in `Data/release-tags/tags.sqlite`. JacRed sends new and changed titles to a local Unix socket. The Jackett search endpoint also fills cache misses. The incremental scanner revisits changed FileDB shards so that parser downtime or a full ingestion queue cannot permanently skip a release.

The vendored JavaScript is the MIT-licensed distribution of `@aiostreams/release-parser` 1.0.1 from [a1d4r's parser at 1630ef2](https://github.com/a1d4r/parse-torrent-title/commit/1630ef2), distributed in [the AIOStreams fork](https://github.com/a1d4r/AIOStreams/commit/92ebfa5). The local rules in `parse.mjs` retain bilingual names and identify explicit subtitle and original-audio language lists. Other unqualified languages cannot identify a particular track. An absent field means the selected parser produced no value.

Consumers can use release tags when a measured value is unavailable. In particular, a season pack's audio and video labels describe the release. Individual file streams belong to the existing ffprobe response. A release-title result does not count as a successful track analysis.

The initial scan reads a master index snapshot and writes into a separate staging directory. It commits title batches and a completed-prefix checkpoint. Repeating an interrupted scan reuses both. The 256 prefix reports describe the first pass over the snapshot. The second read-only pass counts releases with exhausted attempts separately. A newly published torrent can appear between passes. Nightly refresh uses the previous scan start and a short overlap at the mtime boundary. The parser version is tied to the index. Build a fresh staging database before changing parsing rules to avoid reusing old values.

`test.mjs` verifies Russian episode notation and the Venom bilingual release example. Run it with Node 24. The socket path is enabled for JacRed with `JACRED_RELEASE_TAGS_SOCKET`. API results without a socket continue to use existing JacRed metadata.
