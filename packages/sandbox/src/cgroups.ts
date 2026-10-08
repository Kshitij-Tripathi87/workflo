import type { ResourceLimits } from "./spec";

/**
 * cgroups v2 controller — pure computation for write/read plans.
 * Root: /sys/fs/cgroup/workflo/<sandboxId>
 *
 * cpu.max "QUOTA PERIOD": 1 core = 100000/100000; 0.5 core = 50000/100000.
 */

export const CGROUP_FS_ROOT = "/sys/fs/cgroup";

export interface CgroupLayout {
  path: string;
  files: {
    cpuMax: string;
    memoryMax: string;
    pidsMax: string;
    cgroupProcs: string;
    cgroupKill: string;
    cpuStat: string;
    memoryCurrent: string;
    pidsCurrent: string;
  };
}

export function cgroupLayout(sandboxId: string): CgroupLayout {
  const path = `${CGROUP_FS_ROOT}/workflo/${sandboxId}`;
  return {
    path,
    files: {
      cpuMax: `${path}/cpu.max`,
      memoryMax: `${path}/memory.max`,
      pidsMax: `${path}/pids.max`,
      cgroupProcs: `${path}/cgroup.procs`,
      cgroupKill: `${path}/cgroup.kill`,
      cpuStat: `${path}/cpu.stat`,
      memoryCurrent: `${path}/memory.current`,
      pidsCurrent: `${path}/pids.current`,
    },
  };
}

const CPU_PERIOD_US = 100_000;

export function cpuMaxValue(cores: number): string {
  const quota = Math.max(1, Math.floor(cores * CPU_PERIOD_US));
  return `${quota} ${CPU_PERIOD_US}`;
}

export function memoryMaxValue(mb: number): string {
  return String(mb * 1024 * 1024);
}

export function pidsMaxValue(pids: number): string {
  return String(Math.floor(pids));
}

/** The file writes that establish limits for a sandbox. */
export function cgroupLimitWrites(spec: {
  sandboxId: string;
  resources: ResourceLimits;
}): Array<{ file: string; value: string }> {
  const layout = cgroupLayout(spec.sandboxId);
  return [
    { file: layout.files.cpuMax, value: cpuMaxValue(spec.resources.cpu) },
    { file: layout.files.memoryMax, value: memoryMaxValue(spec.resources.memoryMb) },
    { file: layout.files.pidsMax, value: pidsMaxValue(spec.resources.pids) },
  ];
}

/** Writes that attach a process to the cgroup. */
export function cgroupAttachWrite(sandboxId: string, pid: number): { file: string; value: string } {
  return { file: cgroupLayout(sandboxId).files.cgroupProcs, value: String(pid) };
}

/** Writes that freeze-kill every process in the cgroup (kernel 5.14+). */
export function cgroupKillWrite(sandboxId: string): { file: string; value: string } {
  return { file: cgroupLayout(sandboxId).files.cgroupKill, value: "1" };
}

export interface CgroupUsage {
  cpuUsageUsec: number;
  memoryCurrentBytes: number;
  pidsCurrent: number;
}

export function parseCpuStat(content: string): number {
  for (const line of content.split("\n")) {
    const [key, value] = line.trim().split(/\s+/);
    if (key === "usage_usec" && value) return Number(value);
  }
  return 0;
}

export function verifyLimits(
  spec: { sandboxId: string; resources: ResourceLimits },
  readBack: { cpuMax: string; memoryMax: string; pidsMax: string },
): { ok: boolean; mismatches: string[] } {
  const want = {
    cpuMax: cpuMaxValue(spec.resources.cpu),
    memoryMax: memoryMaxValue(spec.resources.memoryMb),
    pidsMax: pidsMaxValue(spec.resources.pids),
  };
  const mismatches: string[] = [];
  if (readBack.cpuMax.trim() !== want.cpuMax) {
    mismatches.push(`cpu.max: want "${want.cpuMax}" got "${readBack.cpuMax.trim()}"`);
  }
  if (readBack.memoryMax.trim() !== want.memoryMax) {
    mismatches.push(`memory.max: want "${want.memoryMax}" got "${readBack.memoryMax.trim()}"`);
  }
  if (readBack.pidsMax.trim() !== want.pidsMax) {
    mismatches.push(`pids.max: want "${want.pidsMax}" got "${readBack.pidsMax.trim()}"`);
  }
  return { ok: mismatches.length === 0, mismatches };
}
