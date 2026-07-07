"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/client";
import { errorMessage, type Workspace } from "@/lib/api/types";
import { workspaceNameSchema } from "@/lib/validation";

function useWorkspaceForm(initialName = "") {
  const [name, setName] = useState(initialName);
  const [validationError, setValidationError] = useState<string | null>(null);

  const validate = (): string | null => {
    const parsed = workspaceNameSchema.safeParse(name);
    if (!parsed.success) {
      setValidationError(parsed.error.issues[0].message);
      return null;
    }
    setValidationError(null);
    return parsed.data;
  };

  return { name, setName, validationError, setValidationError, validate };
}

export function CreateWorkspaceDialog() {
  const [open, setOpen] = useState(false);
  const form = useWorkspaceForm();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (name: string) => {
      const { data, error } = await api.POST("/api/workspaces", { body: { name } });
      if (!data) throw new Error(errorMessage(error, "Could not create workspace"));
      return data;
    },
    onSuccess: (workspace) => {
      toast.success(`Workspace “${workspace.name}” created`);
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      setOpen(false);
      form.setName("");
    },
    onError: (error) => toast.error(error.message),
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const name = form.validate();
    if (name) mutation.mutate(name);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>New workspace</Button>} />
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Create workspace</DialogTitle>
            <DialogDescription>
              A workspace groups the documents for one regulation, standard, or project.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="workspace-name">Name</Label>
            <Input
              id="workspace-name"
              placeholder="e.g. UNECE R155 Cybersecurity"
              value={form.name}
              onChange={(event) => form.setName(event.target.value)}
              autoFocus
            />
            {form.validationError && (
              <p className="text-sm text-destructive">{form.validationError}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function RenameWorkspaceDialog({
  workspace,
  open,
  onOpenChange,
}: {
  workspace: Workspace;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const form = useWorkspaceForm(workspace.name);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (name: string) => {
      const { data, error } = await api.PATCH("/api/workspaces/{workspace_id}", {
        params: { path: { workspace_id: workspace.id } },
        body: { name },
      });
      if (!data) throw new Error(errorMessage(error, "Could not rename workspace"));
      return data;
    },
    onSuccess: () => {
      toast.success("Workspace renamed");
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      onOpenChange(false);
    },
    onError: (error) => toast.error(error.message),
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const name = form.validate();
    if (name) mutation.mutate(name);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Rename workspace</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="rename-workspace-name">Name</Label>
            <Input
              id="rename-workspace-name"
              value={form.name}
              onChange={(event) => form.setName(event.target.value)}
              autoFocus
            />
            {form.validationError && (
              <p className="text-sm text-destructive">{form.validationError}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function DeleteWorkspaceDialog({
  workspace,
  open,
  onOpenChange,
}: {
  workspace: Workspace;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async () => {
      const { error, response } = await api.DELETE("/api/workspaces/{workspace_id}", {
        params: { path: { workspace_id: workspace.id } },
      });
      if (!response.ok) throw new Error(errorMessage(error, "Could not delete workspace"));
    },
    onSuccess: () => {
      toast.success(`Workspace “${workspace.name}” deleted`);
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      onOpenChange(false);
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{workspace.name}”?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes the workspace and all of its documents.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="bg-destructive text-white hover:bg-destructive/90"
          >
            {mutation.isPending ? "Deleting…" : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
