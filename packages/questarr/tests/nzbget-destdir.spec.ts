import { describe, expect, it, vi } from "vitest";
import { NZBGetClient } from "./downloaders/nzbget.js";
import { TransmissionClient } from "./downloaders/transmission.js";

const downloader = (type: string) => ({
  id: "test-downloader",
  name: "Test",
  type,
  url: "http://127.0.0.1",
  port: 5001,
  useSsl: false,
  username: "",
  password: "",
  urlPath: "/xmlrpc",
  enabled: true,
  priority: 1,
  settings: null,
  createdAt: new Date(),
  updatedAt: new Date(),
}) as any;

const successHistory = (overrides: Record<string, unknown> = {}) => ({
  NZBID: 42,
  Name: "fixture-game",
  Status: "SUCCESS/ALL",
  FileSizeMB: 12,
  Category: "questarr",
  DownloadTimeSec: 15,
  ParStatus: "NONE",
  UnpackStatus: "SUCCESS",
  FailedArticles: 0,
  DeleteStatus: "NONE",
  DestDir: "/downloads/foo",
  ...overrides,
});

function nzbget(history: unknown[], active: unknown[] = []) {
  const client = new NZBGetClient(downloader("nzbget"));
  const rpc = vi.spyOn(client as any, "makeXMLRPCRequest").mockImplementation(async (method: unknown) => {
    if (method === "listgroups") return active;
    if (method === "history") return history;
    throw new Error(`unexpected NZBGet method: ${method}`);
  });
  return { client, rpc };
}

describe("Mudos NZBGet completed destination compatibility", () => {
  it("maps the matching successful history DestDir to DownloadDetails.downloadDir", async () => {
    const { client } = nzbget([successHistory()]);
    const details = await client.getDownloadDetails("42");

    expect(details?.status).toBe("completed");
    expect(details?.downloadDir).toBe("/downloads/foo");
    expect(details?.size).toBe(12 * 1024 * 1024);
    expect(details?.progress).toBe(100);
    expect(details?.filesSupport).toBe("unsupported");
  });

  it("does not fabricate downloadDir when successful history omits DestDir", async () => {
    const { client } = nzbget([successHistory({ DestDir: "" })]);
    const details = await client.getDownloadDetails("42");

    expect(details?.status).toBe("completed");
    expect(details).not.toHaveProperty("downloadDir");
  });

  it("does not expose a failed history destination", async () => {
    const { client } = nzbget([
      successHistory({ Status: "FAILURE/ALL", DestDir: "/downloads/failed" }),
    ]);
    const details = await client.getDownloadDetails("42");

    expect(details?.status).toBe("error");
    expect(details).not.toHaveProperty("downloadDir");
  });

  it("keeps active download status and progress without querying a completion path", async () => {
    const { client, rpc } = nzbget([], [{
      NZBID: 42,
      NZBName: "fixture-game",
      Status: "DOWNLOADING",
      FileSizeMB: 12,
      RemainingSizeMB: 3,
      DownloadedSizeMB: 9,
      Category: "questarr",
      DownloadRate: 2048,
      PostInfoText: "",
      PostStageProgress: 0,
      PostStageTimeSec: 0,
    }]);
    const details = await client.getDownloadDetails("42");

    expect(details?.status).toBe("downloading");
    expect(details?.progress).toBe(75);
    expect(details?.downloaded).toBe(9 * 1024 * 1024);
    expect(details).not.toHaveProperty("downloadDir");
    expect(rpc.mock.calls.some(([method]) => method === "history")).toBe(false);
  });

  it("leaves Transmission's native downloadDir mapping unchanged", async () => {
    const client = new TransmissionClient(downloader("transmission"));
    vi.spyOn(client as any, "makeRequest").mockResolvedValue({
      arguments: {
        torrents: [{
          id: 7,
          name: "torrent-game",
          status: 6,
          percentDone: 1,
          rateDownload: 0,
          rateUpload: 0,
          eta: -1,
          totalSize: 100,
          downloadedEver: 100,
          peersSendingToUs: 0,
          peersGettingFromUs: 0,
          uploadRatio: 0,
          errorString: "",
          hashString: "abc",
          downloadDir: "/torrent-downloads/game",
          files: [],
          fileStats: [],
          trackerStats: [],
          peersConnected: 0,
        }],
      },
    });

    const details = await client.getDownloadDetails("7");
    expect(details?.downloadDir).toBe("/torrent-downloads/game");
  });
});
