import createClient from "openapi-fetch";

import type { paths } from "./schema";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export const api = createClient<paths>({ baseUrl: API_BASE_URL });
