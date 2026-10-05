import { describe, expect, it } from "vitest";
import { deviceUrl } from "./deviceUrl";

describe("deviceUrl", () => {
  it("builds the plain address for the default port", () => {
    expect(deviceUrl({ host: "awtrix-cl2.home.lan", port: 80 })).toBe(
      "http://awtrix-cl2.home.lan/",
    );
  });

  it("keeps a port that is not 80", () => {
    expect(deviceUrl({ host: "192.168.11.211", port: 8080 })).toBe(
      "http://192.168.11.211:8080/",
    );
  });

  it("survives a scheme typed despite the form saying not to", () => {
    // Otherwise: http://http//awtrix… — a link that goes nowhere.
    expect(deviceUrl({ host: "http://awtrix-cl1.home.lan", port: 80 })).toBe(
      "http://awtrix-cl1.home.lan/",
    );
    expect(deviceUrl({ host: "HTTPS://awtrix-cl1.home.lan", port: 80 })).toBe(
      "http://awtrix-cl1.home.lan/",
    );
  });

  it("does not double the trailing slash", () => {
    expect(deviceUrl({ host: "awtrix.home.lan/", port: 80 })).toBe(
      "http://awtrix.home.lan/",
    );
  });
});
