import { describe, expect, it } from "vitest";

import { getCommandItems, getItemsWithOrder } from "./sidebar-utils";

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

describe("getItemsWithOrder", () => {
  it("should preserve the defined order for known items", () => {
    const files = ["client.mdx", "installation.mdx", "batch.mdx"];
    const orderedIds = ["guides/installation", "guides/client", "guides/batch"];

    const result = getItemsWithOrder(files, orderedIds, "guides");

    expect(result).toStrictEqual(["guides/installation", "guides/client", "guides/batch"]);
  });

  it("should append new files sorted alphabetically after ordered items", () => {
    const files = ["client.mdx", "installation.mdx", "batch.mdx", "new-guide.mdx", "advanced.mdx"];
    const orderedIds = ["guides/installation", "guides/client", "guides/batch"];

    const result = getItemsWithOrder(files, orderedIds, "guides");

    expect(result).toStrictEqual([
      "guides/installation",
      "guides/client",
      "guides/batch",
      "guides/advanced",
      "guides/new-guide",
    ]);
  });

  it("should skip ordered items that no longer exist on disk", () => {
    const files = ["installation.mdx", "batch.mdx"];
    const orderedIds = ["guides/installation", "guides/client", "guides/batch"];

    const result = getItemsWithOrder(files, orderedIds, "guides");

    expect(result).toStrictEqual(["guides/installation", "guides/batch"]);
  });

  it("should ignore non-mdx files", () => {
    const files = ["installation.mdx", "README.md", ".DS_Store"];
    const orderedIds = ["guides/installation"];

    const result = getItemsWithOrder(files, orderedIds, "guides");

    expect(result).toStrictEqual(["guides/installation"]);
  });

  it("should work without a prefix", () => {
    const files = ["tracking.mdx", "object_file.mdx", "new-topic.mdx"];
    const orderedIds = ["tracking", "object_file"];

    const result = getItemsWithOrder(files, orderedIds);

    expect(result).toStrictEqual(["tracking", "object_file", "new-topic"]);
  });

  it("should return all files sorted when no ordered ids are provided", () => {
    const files = ["batch.mdx", "installation.mdx", "client.mdx"];

    const result = getItemsWithOrder(files, [], "guides");

    expect(result).toStrictEqual(["guides/batch", "guides/client", "guides/installation"]);
  });
});
