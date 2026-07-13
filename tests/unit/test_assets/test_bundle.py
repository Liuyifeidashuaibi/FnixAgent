"""
资产包加载/保存测试。

覆盖:
    - 往返一致性: save -> load 后数据等价
    - 缺失文件处理: 从空/部分目录加载不抛异常
    - 版本信息: version / created_at 保留
    - 文件布局: 各资产文件按预期路径生成
"""
import json
import os

import pytest

from fnixagent.assets.bundle import (
    ASSETS_VERSION,
    AssetsBundle,
    load_assets,
    save_assets,
)
from fnixagent.core.types import SkillLevel


# ---------------------------------------------------------------------------
# 往返一致性
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """save -> load 往返一致性。"""

    def test_round_trip_preserves_topology(self, sample_bundle, tmp_bundle_dir):
        """拓扑快照往返一致。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        loaded = load_assets(tmp_bundle_dir)
        assert loaded.topology_snapshot == sample_bundle.topology_snapshot
        assert len(loaded.topology_snapshot["nodes"]) == 2
        assert len(loaded.topology_snapshot["edges"]) == 1

    def test_round_trip_preserves_skills(self, sample_bundle, tmp_bundle_dir):
        """技能注册表往返一致(含枚举还原)。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        loaded = load_assets(tmp_bundle_dir)
        assert len(loaded.skills_registry) == 2
        original = sample_bundle.skills_registry
        for got, exp in zip(loaded.skills_registry, original):
            assert got.name == exp.name
            assert got.skill_level == exp.skill_level
            assert got.bound_concept_id == exp.bound_concept_id
            assert got.priority == exp.priority
            assert got.success_count == exp.success_count
            assert got.failure_count == exp.failure_count
            assert got.last_invoked_at == exp.last_invoked_at

    def test_round_trip_preserves_flywheel_history(self, sample_bundle, tmp_bundle_dir):
        """飞轮历史往返一致。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        loaded = load_assets(tmp_bundle_dir)
        assert loaded.flywheel_history == sample_bundle.flywheel_history
        assert len(loaded.flywheel_history) == 2

    def test_round_trip_preserves_traces(self, sample_bundle, tmp_bundle_dir):
        """轨迹归档往返一致。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        loaded = load_assets(tmp_bundle_dir)
        assert loaded.traces_archive == sample_bundle.traces_archive
        assert len(loaded.traces_archive) == 2

    def test_round_trip_preserves_prompts(self, sample_bundle, tmp_bundle_dir):
        """提示词往返一致。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        loaded = load_assets(tmp_bundle_dir)
        assert loaded.prompts == sample_bundle.prompts
        assert "system.yaml" in loaded.prompts
        assert "reflection.yaml" in loaded.prompts

    def test_round_trip_preserves_version_info(self, sample_bundle, tmp_bundle_dir):
        """版本与创建时间往返一致。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        loaded = load_assets(tmp_bundle_dir)
        assert loaded.version == sample_bundle.version
        assert loaded.created_at == sample_bundle.created_at


# ---------------------------------------------------------------------------
# 缺失文件处理
# ---------------------------------------------------------------------------

class TestMissingFiles:
    """缺失文件应按空值兜底,不抛异常。"""

    def test_load_empty_dir(self, tmp_bundle_dir):
        """从空目录加载,所有字段为默认空值。"""
        loaded = load_assets(tmp_bundle_dir)
        assert loaded.topology_snapshot == {}
        assert loaded.skills_registry == []
        assert loaded.flywheel_history == []
        assert loaded.traces_archive == []
        assert loaded.prompts == {}
        # 版本兜底为默认值
        assert loaded.version == ASSETS_VERSION
        assert isinstance(loaded.created_at, float)

    def test_load_partial_dir_missing_topology(self, sample_bundle, tmp_bundle_dir):
        """删除 topology 目录后加载,拓扑为空但其余资产正常。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        # 删除 topology 目录
        topo_path = os.path.join(tmp_bundle_dir, "topology", "snapshot.json")
        os.remove(topo_path)
        loaded = load_assets(tmp_bundle_dir)
        assert loaded.topology_snapshot == {}
        assert len(loaded.skills_registry) == 2

    def test_load_partial_dir_missing_skills(self, sample_bundle, tmp_bundle_dir):
        """删除 skills 目录后加载,技能为空但其余资产正常。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        skills_path = os.path.join(tmp_bundle_dir, "skills", "registry.json")
        os.remove(skills_path)
        loaded = load_assets(tmp_bundle_dir)
        assert loaded.skills_registry == []
        assert len(loaded.topology_snapshot["nodes"]) == 2

    def test_load_partial_dir_missing_jsonl(self, sample_bundle, tmp_bundle_dir):
        """删除 JSONL 文件后加载,对应字段为空列表。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        os.remove(os.path.join(tmp_bundle_dir, "flywheel", "history.jsonl"))
        os.remove(os.path.join(tmp_bundle_dir, "traces", "traces.jsonl"))
        loaded = load_assets(tmp_bundle_dir)
        assert loaded.flywheel_history == []
        assert loaded.traces_archive == []


# ---------------------------------------------------------------------------
# 版本信息
# ---------------------------------------------------------------------------

class TestVersionInfo:
    """版本元信息测试。"""

    def test_version_file_written(self, sample_bundle, tmp_bundle_dir):
        """保存后 meta/version.json 存在且含 version/created_at。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        version_path = os.path.join(tmp_bundle_dir, "meta", "version.json")
        assert os.path.exists(version_path)
        with open(version_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["version"] == sample_bundle.version
        assert meta["created_at"] == sample_bundle.created_at
        assert "saved_at" in meta

    def test_custom_version_preserved(self, tmp_bundle_dir):
        """自定义版本号能被正确保留。"""
        bundle = AssetsBundle(version="2.3.1", created_at=1234567890.0)
        save_assets(bundle, tmp_bundle_dir)
        loaded = load_assets(tmp_bundle_dir)
        assert loaded.version == "2.3.1"
        assert loaded.created_at == 1234567890.0


# ---------------------------------------------------------------------------
# 文件布局
# ---------------------------------------------------------------------------

class TestFileLayout:
    """验证资产文件按预期路径生成。"""

    def test_all_expected_files_exist(self, sample_bundle, tmp_bundle_dir):
        """保存后所有预期文件路径均存在。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        expected = [
            os.path.join("topology", "snapshot.json"),
            os.path.join("skills", "registry.json"),
            os.path.join("flywheel", "history.jsonl"),
            os.path.join("traces", "traces.jsonl"),
            os.path.join("prompts", "system.yaml"),
            os.path.join("prompts", "reflection.yaml"),
            os.path.join("meta", "version.json"),
        ]
        for rel in expected:
            assert os.path.exists(os.path.join(tmp_bundle_dir, rel)), f"缺失文件: {rel}"

    def test_jsonl_format(self, sample_bundle, tmp_bundle_dir):
        """JSONL 文件每行一条有效 JSON。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        traces_path = os.path.join(tmp_bundle_dir, "traces", "traces.jsonl")
        with open(traces_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "trace_id" in data

    def test_json_ensure_ascii_false(self, sample_bundle, tmp_bundle_dir):
        """JSON 文件使用 ensure_ascii=False(中文字符不转义)。"""
        save_assets(sample_bundle, tmp_bundle_dir)
        topo_path = os.path.join(tmp_bundle_dir, "topology", "snapshot.json")
        with open(topo_path, "r", encoding="utf-8") as f:
            raw = f.read()
        # 中文名称应直接出现在文件中,而非 \uXXXX 转义
        assert "撰写论文综述" in raw


# ---------------------------------------------------------------------------
# 技能记录枚举还原
# ---------------------------------------------------------------------------

class TestSkillRecordSerialization:
    """SkillRecord 枚举字段序列化/反序列化。"""

    def test_skill_level_enum_restored(self, tmp_bundle_dir):
        """技能级别枚举正确还原为 SkillLevel。"""
        from fnixagent.assets.bundle import (
            skill_record_from_dict,
            skill_record_to_dict,
        )
        from fnixagent.core.types import SkillRecord

        record = SkillRecord(
            name="meta_skill",
            skill_level=SkillLevel.META,
            bound_concept_id="L2:c1",
            priority=0.9,
        )
        d = skill_record_to_dict(record)
        assert d["skill_level"] == "meta"
        restored = skill_record_from_dict(d)
        assert restored.skill_level == SkillLevel.META

    def test_invalid_skill_level_falls_back_to_basic(self):
        """无效的 skill_level 字符串回退到 BASIC。"""
        from fnixagent.assets.bundle import skill_record_from_dict

        d = {"name": "x", "skill_level": "unknown_level"}
        record = skill_record_from_dict(d)
        assert record.skill_level == SkillLevel.BASIC
