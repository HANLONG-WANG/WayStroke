// Generated from waystroke-protocol; do not edit.
import type {Config,ValidationError} from './model';
export const PROTOCOL_VERSION = 1;
export type Snapshot = { revision: number, savedAt: string | null, config: Config, };
export type Commit = { requestId: string, expectedRevision: number, config: Config, };
export type ErrorKind = "validation" | "conflict" | "permission" | "unavailable" | "targetInvalid" | "timeout" | "canceled" | "io" | "internal";
export type Error = { kind: ErrorKind, message: string, details: Array<ValidationError>, };
export type Reply<T> = { "status": "ok", value: T, } | { "status": "error", error: Error, };
export type Status = { protocolVersion: number, coreVersion: string, extensionConnected: boolean, inputConnected: boolean, executionAvailable: boolean, reason: string, };
