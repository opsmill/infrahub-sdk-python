import { describe, expect, it } from "vitest";

import { getCommandItems } from "./sidebar-utils";

describe("getCommandItems", () => {
  it("should filter and sort mdx command files", () => {
    const files = [
      "infrahubctl.mdx",
      "infrahubctl-branch.mdx",
      "infrahubctl-validate.mdx",
      "infrahubctl-check.mdx",
    ];

    const result = getCommandItems(files);

    expect(result).toStrictEqual([
      "infrahubctl-branch",
      "infrahubctl-check",
      "infrahubctl-validate",
    ]);
  });

  it("should exclude the index file", () => {
    const files = ["infrahubctl.mdx", "infrahubctl-branch.mdx"];

    const result = getCommandItems(files);

    expect(result).toStrictEqual(["infrahubctl-branch"]);
  });

  it("should ignore non-mdx files", () => {
    const files = ["infrahubctl-branch.mdx", "README.md", ".DS_Store", "image.png"];

    const result = getCommandItems(files);

    expect(result).toStrictEqual(["infrahubctl-branch"]);
  });

  it("should return an empty array when only the index file exists", () => {
    const result = getCommandItems(["infrahubctl.mdx"]);

    expect(result).toStrictEqual([]);
  });

  it("should return an empty array for an empty directory", () => {
    const result = getCommandItems([]);

    expect(result).toStrictEqual([]);
  });

  it("should support a custom index file name", () => {
    const files = ["index.mdx", "command-a.mdx", "command-b.mdx"];

    const result = getCommandItems(files, "index.mdx");

    expect(result).toStrictEqual(["command-a", "command-b"]);
  });
});
