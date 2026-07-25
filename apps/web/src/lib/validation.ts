import { z } from "zod";

export const workspaceNameSchema = z
  .string()
  .trim()
  .min(1, "Name is required")
  .max(200, "Name must be at most 200 characters");

// Same shape/pattern the API uses (apps/api/src/atip_api/schemas/auth.py).
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * Client-side signup validation, kept in lock-step with the API's
 * RegisterRequest + password policy. The server re-validates everything; this
 * is UX only (fast inline feedback), never a security boundary.
 */
export const registerSchema = z
  .object({
    displayName: z
      .string()
      .trim()
      .min(1, "Your name is required")
      .max(200, "Name must be at most 200 characters"),
    email: z
      .string()
      .trim()
      .min(1, "Email is required")
      .max(320, "Email is too long")
      .regex(EMAIL_PATTERN, "Enter a valid email address"),
    organizationName: z
      .string()
      .trim()
      .min(1, "Organization name is required")
      .max(200, "Organization name must be at most 200 characters"),
    password: z
      .string()
      .min(8, "Use at least 8 characters")
      .max(72, "Use at most 72 characters")
      .regex(/[A-Za-z]/, "Add at least one letter")
      .regex(/\d/, "Add at least one number"),
    confirmPassword: z.string().min(1, "Confirm your password"),
    acceptedTerms: z
      .boolean()
      .refine((v) => v === true, { message: "Please accept the terms to continue" }),
  })
  .refine((v) => v.password.trim().toLowerCase() !== v.email.trim().toLowerCase(), {
    message: "Password must not be the same as your email",
    path: ["password"],
  })
  .refine((v) => v.password === v.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

export type RegisterInput = z.infer<typeof registerSchema>;

/** First error message per field, for inline display next to each input. */
export function fieldErrorsFrom(error: z.ZodError): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const issue of error.issues) {
    const key = String(issue.path[0] ?? "");
    if (key && !(key in errors)) errors[key] = issue.message;
  }
  return errors;
}
