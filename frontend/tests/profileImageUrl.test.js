import test from "node:test";
import assert from "node:assert/strict";
import { profileImageUrl } from "../src/utils/profileImageUrl.js";

test("profile image paths are resolved against the API origin", () => {
  assert.equal(
    profileImageUrl("uploads/profiles/avatar.jpg?expires=123&signature=abc", "https://api.example.test/"),
    "https://api.example.test/uploads/profiles/avatar.jpg?expires=123&signature=abc",
  );
});

test("absolute profile image URLs and empty values stay unchanged", () => {
  assert.equal(profileImageUrl("https://cdn.example.test/avatar.jpg", "https://api.example.test"), "https://cdn.example.test/avatar.jpg");
  assert.equal(profileImageUrl(null, "https://api.example.test"), undefined);
});
