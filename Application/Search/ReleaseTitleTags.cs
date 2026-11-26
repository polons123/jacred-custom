using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Net.Sockets;
using System.Text.Json;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using JacRed.Models.Api;

namespace JacRed.Application.Search
{
    internal static class ReleaseTitleTags
    {
        static readonly string SocketPath = Environment.GetEnvironmentVariable("JACRED_RELEASE_TAGS_SOCKET");
        static readonly HttpClient Client = new(new SocketsHttpHandler {
            ConnectCallback = async (context, ct) => {
                var socket = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
                try {
                    await socket.ConnectAsync(new UnixDomainSocketEndPoint(SocketPath), ct);
                    return new NetworkStream(socket, ownsSocket: true);
                } catch {
                    socket.Dispose();
                    throw;
                }
            }
        }) { BaseAddress = new Uri("http://localhost"), Timeout = TimeSpan.FromSeconds(3) };

        static readonly Channel<string> Pending = Channel.CreateBounded<string>(new BoundedChannelOptions(4096) {
            SingleReader = true, FullMode = BoundedChannelFullMode.DropWrite
        });

        static ReleaseTitleTags()
        {
            if (!string.IsNullOrEmpty(SocketPath))
                _ = Task.Run(Drain);
        }

        internal static void Record(string title)
        {
            if (!string.IsNullOrEmpty(SocketPath) && !string.IsNullOrWhiteSpace(title) && title.Length <= 32768)
                Pending.Writer.TryWrite(title);
        }

        static async Task<JsonElement[]> Fetch(string[] titles, CancellationToken ct)
        {
            using var response = await Client.PostAsJsonAsync("/titles", titles, ct);
            response.EnsureSuccessStatusCode();
            var tags = await response.Content.ReadFromJsonAsync<JsonElement[]>(cancellationToken: ct);
            if (tags?.Length != titles.Length) throw new JsonException("Release tag count mismatch");
            return tags;
        }

        static bool Unavailable(Exception ex) => ex is HttpRequestException or OperationCanceledException or JsonException or IOException;

        static async Task Drain()
        {
            while (await Pending.Reader.WaitToReadAsync()) {
                var titles = new HashSet<string>();
                while (titles.Count < 128 && Pending.Reader.TryRead(out var title)) titles.Add(title);
                // Changed shards are also revisited by the incremental scanner.
                try { await Fetch(titles.ToArray(), CancellationToken.None); }
                catch (Exception ex) when (Unavailable(ex)) { await Task.Delay(1000); }
            }
        }

        internal static async Task<List<Result>> Enrich(List<Result> rows, CancellationToken ct)
        {
            if (string.IsNullOrEmpty(SocketPath) || rows.Count == 0) return rows;
            var titles = rows.Where(r => r.info != null && r.Title?.Length is > 0 and <= 32768)
                             .Select(r => r.Title).Distinct().ToArray();
            var byTitle = new Dictionary<string, JsonElement>();
            try {
                foreach (var chunk in titles.Chunk(128)) {
                    var tags = await Fetch(chunk, ct);
                    for (int i = 0; i < tags.Length; i++) byTitle[chunk[i]] = tags[i];
                }
            } catch (Exception ex) when (Unavailable(ex) && !ct.IsCancellationRequested) {
                // Keep the ordinary search available while the optional index is unavailable.
            }
            if (byTitle.Count == 0) return rows;
            var enriched = new List<Result>(rows.Count);
            foreach (var row in rows) {
                if (row.info == null || row.Title == null || !byTitle.TryGetValue(row.Title, out var tags)) {
                    enriched.Add(row);
                    continue;
                }
                var copy = row.Clone();
                copy.info.releaseTags = tags;
                enriched.Add(copy);
            }
            return enriched;
        }
    }
}
