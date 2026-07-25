"use client";

import { Check, CircleAlert, Loader2, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/types";
import { fieldErrorsFrom, registerSchema } from "@/lib/validation";

type Fields = {
  displayName: string;
  email: string;
  organizationName: string;
  password: string;
  confirmPassword: string;
  acceptedTerms: boolean;
};

const EMPTY: Fields = {
  displayName: "",
  email: "",
  organizationName: "",
  password: "",
  confirmPassword: "",
  acceptedTerms: false,
};

// Maps a conflicting-email/org 409 back onto the field that caused it.
const CONFLICT_FIELD: Record<string, keyof Fields> = {
  email_already_registered: "email",
  organization_exists: "organizationName",
};

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs text-destructive-strong">
      {message}
    </p>
  );
}

function SignupForm() {
  const router = useRouter();
  const [fields, setFields] = useState<Fields>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const set = <K extends keyof Fields>(key: K, value: Fields[K]) => {
    setFields((prev) => ({ ...prev, [key]: value }));
    // clear a field's error as the user corrects it
    setErrors((prev) => (prev[key] ? { ...prev, [key]: "" } : prev));
  };

  // Live password rules (mirrors the server policy) for clear, honest feedback.
  const rules = useMemo(
    () => [
      { label: "8–72 characters", ok: fields.password.length >= 8 && fields.password.length <= 72 },
      { label: "A letter", ok: /[A-Za-z]/.test(fields.password) },
      { label: "A number", ok: /\d/.test(fields.password) },
    ],
    [fields.password],
  );

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (pending) return;
    setFormError(null);

    const parsed = registerSchema.safeParse(fields);
    if (!parsed.success) {
      setErrors(fieldErrorsFrom(parsed.error));
      return;
    }
    setErrors({});
    setPending(true);

    const { data, error } = await api.POST("/api/auth/register", {
      body: {
        display_name: parsed.data.displayName,
        email: parsed.data.email,
        organization_name: parsed.data.organizationName,
        password: parsed.data.password,
      },
    });

    if (!data) {
      const code = error && typeof error === "object" && "code" in error ? String(error.code) : "";
      const field = CONFLICT_FIELD[code];
      const message = errorMessage(error, "Could not create your account. Please try again.");
      if (field) {
        setErrors({ [field]: message });
      } else {
        setFormError(message);
      }
      setPending(false);
      return;
    }

    // registration logs the user straight in (session cookie is set); land them
    // on the dashboard and refresh so the authenticated shell renders.
    router.replace("/");
    router.refresh();
  };

  return (
    <div className="mx-auto mt-16 mb-16 w-full max-w-sm">
      <div className="mb-6 text-center">
        <p className="font-serif text-2xl font-semibold tracking-tight">ATIP</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Automotive Technical Intelligence Platform
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Create your account</CardTitle>
          <CardDescription>
            Set up a new organization workspace for verified compliance and engineering
            document analysis.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="displayName">Full name</Label>
              <Input
                id="displayName"
                autoComplete="name"
                required
                value={fields.displayName}
                onChange={(event) => set("displayName", event.target.value)}
                aria-invalid={Boolean(errors.displayName)}
                aria-describedby={errors.displayName ? "displayName-error" : undefined}
              />
              <FieldError id="displayName-error" message={errors.displayName} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="email">Work email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={fields.email}
                onChange={(event) => set("email", event.target.value)}
                aria-invalid={Boolean(errors.email)}
                aria-describedby={errors.email ? "email-error" : undefined}
              />
              <FieldError id="email-error" message={errors.email} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="organizationName">Company / organization</Label>
              <Input
                id="organizationName"
                autoComplete="organization"
                required
                value={fields.organizationName}
                onChange={(event) => set("organizationName", event.target.value)}
                aria-invalid={Boolean(errors.organizationName)}
                aria-describedby={errors.organizationName ? "organizationName-error" : undefined}
              />
              <FieldError id="organizationName-error" message={errors.organizationName} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                value={fields.password}
                onChange={(event) => set("password", event.target.value)}
                aria-invalid={Boolean(errors.password)}
                aria-describedby={errors.password ? "password-error" : "password-rules"}
              />
              <FieldError id="password-error" message={errors.password} />
              <ul id="password-rules" className="flex flex-wrap gap-x-3 gap-y-1">
                {rules.map((rule) => (
                  <li
                    key={rule.label}
                    className={
                      "flex items-center gap-1 text-xs " +
                      (rule.ok ? "text-success-strong" : "text-muted-foreground")
                    }
                  >
                    <Check className={"size-3 " + (rule.ok ? "opacity-100" : "opacity-40")} />
                    {rule.label}
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm password</Label>
              <Input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                value={fields.confirmPassword}
                onChange={(event) => set("confirmPassword", event.target.value)}
                aria-invalid={Boolean(errors.confirmPassword)}
                aria-describedby={errors.confirmPassword ? "confirmPassword-error" : undefined}
              />
              <FieldError id="confirmPassword-error" message={errors.confirmPassword} />
            </div>

            <div className="space-y-2">
              <label htmlFor="acceptedTerms" className="flex items-start gap-2 text-sm">
                <input
                  id="acceptedTerms"
                  type="checkbox"
                  className="mt-0.5 size-4 shrink-0 rounded border-input accent-primary"
                  checked={fields.acceptedTerms}
                  onChange={(event) => set("acceptedTerms", event.target.checked)}
                  aria-invalid={Boolean(errors.acceptedTerms)}
                  aria-describedby={errors.acceptedTerms ? "acceptedTerms-error" : undefined}
                />
                <span className="text-muted-foreground">
                  I agree to ATIP&apos;s{" "}
                  <span className="font-medium text-foreground">Terms of Service</span> and{" "}
                  <span className="font-medium text-foreground">Privacy Policy</span>.
                </span>
              </label>
              <FieldError id="acceptedTerms-error" message={errors.acceptedTerms} />
            </div>

            {formError && (
              <p
                className="flex items-start gap-2 rounded-lg border border-destructive/25 bg-destructive-soft px-3 py-2 text-sm text-destructive-strong"
                role="alert"
              >
                <CircleAlert className="mt-0.5 size-4 shrink-0" />
                {formError}
              </p>
            )}

            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <UserPlus className="size-4" />
              )}
              Create account
            </Button>
          </form>
        </CardContent>
      </Card>
      <p className="mt-4 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}

export default function SignupPage() {
  return <SignupForm />;
}
