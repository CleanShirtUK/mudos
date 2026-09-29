import { access } from "node:fs/promises";
import { constants } from "node:fs";
import path from "node:path";
import { NZBGetClient } from "/app/dist/server/downloaders/nzbget.js";

const downloadDir = process.env.QUESTARR_VERIFY_DESTDIR;
if (!downloadDir || !downloadDir.startsWith("/home/lulu/Games/.acquisition/usenet/complete/")) {
  throw new Error("verification destination is not in Questarr's completed-output mount");
}
await access(downloadDir, constants.R_OK | constants.X_OK);
const normalizedDir = downloadDir.replace(/[\\/]+$/, "");
const name = path.basename(normalizedDir);
const buildRemoteImportPath = (dir, downloadName) => {
  const lastSegment = dir.split(/[\\/]/).pop()?.toLowerCase();
  return lastSegment === downloadName.toLowerCase() ? dir : `${dir}/${downloadName}`;
};

const client = new NZBGetClient({
  id: "mudos-runtime-verification",
  name: "Mudos runtime verification",
  type: "nzbget",
  url: "http://127.0.0.1",
  port: 5001,
  useSsl: false,
  username: "",
  password: "",
  urlPath: "/xmlrpc",
  enabled: true,
  priority: 1,
});
client.makeXMLRPCRequest = async (method) => {
  if (method === "listgroups") return [];
  if (method === "history") {
    return [{
      NZBID: 9000001,
      Name: name,
      Status: "SUCCESS/ALL",
      FileSizeMB: 0,
      Category: "questarr",
      DownloadTimeSec: 0,
      ParStatus: "NONE",
      UnpackStatus: "SUCCESS",
      FailedArticles: 0,
      DeleteStatus: "NONE",
      DestDir: downloadDir,
    }];
  }
  throw new Error(`Unexpected verification XML-RPC method: ${method}`);
};

const details = await client.getDownloadDetails("9000001");
if (details?.status !== "completed" || details.downloadDir !== downloadDir) {
  throw new Error("patched NZBGet client did not propagate the completed destination");
}
const importerPath = buildRemoteImportPath(normalizedDir, details.name);
await access(importerPath, constants.R_OK | constants.X_OK);
if (path.resolve(importerPath) !== path.resolve(downloadDir)) {
  throw new Error("Questarr automatic-import path builder changed the verified source path");
}
console.log(JSON.stringify({ status: details.status, downloadDir: details.downloadDir, importerPath }));
