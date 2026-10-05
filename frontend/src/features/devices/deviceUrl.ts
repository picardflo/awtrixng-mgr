import type { Device } from "../../api/client";

/**
 * The display's own web interface.
 *
 * Plain http: the firmware serves nothing else. Any scheme is stripped from
 * the stored host in case someone typed one despite the form saying not to,
 * which would otherwise build `http://http//…` and a dead link.
 */
export function deviceUrl(device: Pick<Device, "host" | "port">): string {
  const host = device.host.replace(/^https?:\/\//i, "").replace(/\/+$/, "");
  const port = device.port === 80 ? "" : `:${device.port}`;
  return `http://${host}${port}/`;
}
