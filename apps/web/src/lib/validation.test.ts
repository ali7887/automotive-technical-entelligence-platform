import { describe, expect, it } from "vitest";

import { fieldErrorsFrom, registerSchema } from "./validation";

const VALID = {
  displayName: "Dana Engineer",
  email: "dana@newco.test",
  organizationName: "NewCo Automotive",
  password: "correct-horse-9",
  confirmPassword: "correct-horse-9",
  acceptedTerms: true,
};

/** The field key each failing input should surface an error on. */
function errorFields(input: Record<string, unknown>): string[] {
  const result = registerSchema.safeParse(input);
  if (result.success) return [];
  return Object.keys(fieldErrorsFrom(result.error));
}

describe("registerSchema", () => {
  it("accepts a well-formed signup and trims whitespace", () => {
    const result = registerSchema.safeParse({
      ...VALID,
      displayName: "  Dana Engineer  ",
      email: "  dana@newco.test  ",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.displayName).toBe("Dana Engineer");
      expect(result.data.email).toBe("dana@newco.test");
    }
  });

  it("mirrors the server password policy", () => {
    expect(errorFields({ ...VALID, password: "short-1", confirmPassword: "short-1" })).toContain(
      "password",
    );
    expect(
      errorFields({ ...VALID, password: "no-digits-here", confirmPassword: "no-digits-here" }),
    ).toContain("password");
    expect(errorFields({ ...VALID, password: "12345678", confirmPassword: "12345678" })).toContain(
      "password",
    );
  });

  it("rejects a password equal to the email", () => {
    const input = {
      ...VALID,
      email: "dana1@newco.test",
      password: "dana1@newco.test",
      confirmPassword: "dana1@newco.test",
    };
    expect(errorFields(input)).toContain("password");
  });

  it("requires the confirmation to match", () => {
    expect(errorFields({ ...VALID, confirmPassword: "different-9" })).toContain("confirmPassword");
  });

  it("requires accepting the terms and a valid email", () => {
    expect(errorFields({ ...VALID, acceptedTerms: false })).toContain("acceptedTerms");
    expect(errorFields({ ...VALID, email: "not-an-email" })).toContain("email");
  });
});
