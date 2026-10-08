import { describe, expect, it } from "vitest";
import {
  cgroupLayout,
  cpuMaxValue,
  memoryMaxValue,
  pidsMaxValue,
  cgroupLimitWrites,
  cgroupAttachWrite,
  cgroupKillWrite,
  parseCpuStat,
  verifyLimits,
} from "../src/cgroups";
import { makeSpec } from "./helpers";

describe("cgroups v2", () => {
  it("cpu.max: 2 cores = '200000 100000', 0.5 = '50000 100000'", () => {
    expect(cpuMaxValue(2)).toBe("200000 100000");
    expect(cpuMaxValue(0.5)).toBe("50000 100000");
    expect(cpuMaxValue(0.001)).toBe("100 100000"); // floor at 1µs quota
  });

  it("memory.max and pids.max are plain bytes/count", () => {
    expect(memoryMaxValue(1024)).toBe(String(1024 * 1024 * 1024));
    expect(pidsMaxValue(128)).toBe("128");
  });

  it("layout is rooted at /sys/fs/cgroup/workflo/<id>", () => {
    const layout = cgroupLayout("sbx-test01");
    expect(layout.path).toBe("/sys/fs/cgroup/workflo/sbx-test01");
    expect(layout.files.cpuMax).toBe("/sys/fs/cgroup/workflo/sbx-test01/cpu.max");
  });

  it("limit write plan covers cpu, memory, pids", () => {
    const spec = makeSpec();
    const writes = cgroupLimitWrites(spec);
    expect(writes).toEqual([
      { file: "/sys/fs/cgroup/workflo/sbx-test01/cpu.max", value: "200000 100000" },
      { file: "/sys/fs/cgroup/workflo/sbx-test01/memory.max", value: String(1024 * 1024 * 1024) },
      { file: "/sys/fs/cgroup/workflo/sbx-test01/pids.max", value: "128" },
    ]);
  });

  it("attach + kill plans target the right files", () => {
    expect(cgroupAttachWrite("sbx-test01", 4242)).toEqual({
      file: "/sys/fs/cgroup/workflo/sbx-test01/cgroup.procs",
      value: "4242",
    });
    expect(cgroupKillWrite("sbx-test01")).toEqual({
      file: "/sys/fs/cgroup/workflo/sbx-test01/cgroup.kill",
      value: "1",
    });
  });

  it("parseCpuStat extracts usage_usec", () => {
    expect(parseCpuStat("usage_usec 1234567\nuser_usec 1000\nsystem_usec 200\n")).toBe(1234567);
    expect(parseCpuStat("")).toBe(0);
  });

  it("verifyLimits detects drift", () => {
    const spec = makeSpec();
    const good = verifyLimits(spec, {
      cpuMax: "200000 100000",
      memoryMax: String(1024 * 1024 * 1024),
      pidsMax: "128",
    });
    expect(good.ok).toBe(true);

    const bad = verifyLimits(spec, {
      cpuMax: "max 100000",
      memoryMax: String(1024 * 1024 * 1024),
      pidsMax: "128",
    });
    expect(bad.ok).toBe(false);
    expect(bad.mismatches[0]).toContain("cpu.max");
  });
});
