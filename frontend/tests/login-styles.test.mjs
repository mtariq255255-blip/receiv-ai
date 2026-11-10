import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const loginComponent = readFileSync(
  new URL("../components/LoginPage.tsx", import.meta.url),
  "utf8"
);
const globalStyles = readFileSync(
  new URL("../app/globals.css", import.meta.url),
  "utf8"
);

test("login page classes have matching stylesheet rules", () => {
  const classes = [
    "receivai-login",
    "login-intro",
    "login-form-side",
    "login-panel",
    "login-input",
    "login-submit",
  ];

  for (const className of classes) {
    assert.ok(
      loginComponent.includes(className),
      `LoginPage should use the ${className} class`
    );
    assert.match(
      globalStyles,
      new RegExp(`\\.${className}(?=[\\s.:,{])`),
      `globals.css should style the ${className} class`
    );
  }
});
