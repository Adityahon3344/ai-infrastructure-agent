export interface Server {
  id: string;
  name: string;
  hostname: string;
  ip_address: string;
  port: number;
  username: string;
  os_family: string;
  os_distribution: string;
  os_version: string;
  architecture: string;
  environment: string;
  tags: Record<string, string>;
  connection_id: string | null;
  status: "unknown" | "online" | "offline" | "warning" | "critical";
  last_seen: string | null;
  cpu_cores: number | null;
  ram_mb: number | null;
  disk_gb: number | null;
  capabilities: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Connection {
  id: string;
  name: string;
  type: "ssh" | "aws" | "azure" | "gcp" | "kubernetes";
  status: "unknown" | "valid" | "invalid" | "disabled";
  disabled: boolean;
  config: Record<string, unknown>;
  account_info: Record<string, unknown>;
  last_tested_at: string | null;
  last_used_at: string | null;
  last_test_message: string;
  created_at: string;
}

export interface PlanPreview {
  summary: string;
  targets: { id: string; name: string; hostname: string; environment: string; os: string }[];
  steps: { action: string; description: string }[];
  expected_changes: string[];
  no_changes_note: string | null;
  risk_level: "low" | "medium" | "high";
  risk_reasons: string[];
  job_id: string;
}

export interface Approval {
  id: string;
  action_summary: string;
  target_summary: string;
  expected_changes: string[];
  risk_level: string;
  impact: string;
}

export interface ChatResponse {
  conversation_id: string;
  message: string;
  needs_server_selection: boolean;
  server_options: { id: string; name: string; hostname: string; environment: string; os: string }[];
  needs_connection: boolean;
  needs_clarification: boolean;
  plan_preview: PlanPreview | null;
  job_id: string | null;
  approval: Approval | null;
  risk_level: string | null;
}

export interface Job {
  id: string;
  prompt: string;
  plan: any;
  risk_level: string;
  risk_reasons: string[];
  target_server_ids: string[];
  status: string;
  per_target_status: Record<string, string>;
  verification: Record<string, unknown>;
  error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
