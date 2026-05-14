"""覆盖全部 9 个脚本 + 边界情况，74+ 测试"""
import os, sys, re, unittest
sys.path.insert(0, os.path.dirname(__file__))
from main import ScriptParser

def load(fn):
    with open(fn, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def all_cmds(steps):
    r = []
    for _, l in steps:
        r.extend(ScriptParser.extract_commands(l))
    return r

def has_unresolved(cmds):
    return any(c.startswith('>>> [pica,') for c in cmds)

def steps_missing_tag(steps):
    """有命令但没有设备标记的 Step 数"""
    n = 0
    for _, lines in steps:
        cmds = ScriptParser.extract_commands(lines)
        real = [c for c in cmds if not c.startswith('>>>') and c != 'commit']
        if real and not any(c.startswith('>>>') for c in cmds):
            n += 1
    return n


# ============================================================
# 跨脚本通用验证 (最重要)
# ============================================================
class TestAllScripts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {}
        for fn in os.listdir('.'):
            if (fn.startswith('pica8') or fn.startswith('bgp')) and fn.endswith('.txt'):
                steps = ScriptParser.parse_steps(load(fn))
                cls.data[fn] = steps

    def test_all_have_steps(self):
        for fn, steps in self.data.items():
            self.assertGreater(len(steps), 0, f"{fn}")

    def test_no_unresolved_tags(self):
        for fn, steps in self.data.items():
            self.assertFalse(has_unresolved(all_cmds(steps)), f"{fn} 有 pica,N 未解析")

    def test_all_steps_have_device_tag(self):
        """每个有命令的 Step 都必须有设备标记"""
        for fn, steps in self.data.items():
            n = steps_missing_tag(steps)
            self.assertEqual(n, 0, f"{fn}: {n} 个 Step 有命令但无设备标记")

    def test_no_skip_commands(self):
        for fn, steps in self.data.items():
            for c in all_cmds(steps):
                if c.startswith('>>>') or c == 'commit': continue
                self.assertFalse(c.startswith('cat '), f"{fn}: {c}")
                self.assertFalse(c.startswith('ps '), f"{fn}: {c}")
                self.assertFalse(c.startswith('grep '), f"{fn}: {c}")

    def test_no_empty_commands(self):
        for fn, steps in self.data.items():
            for c in all_cmds(steps):
                self.assertTrue(len(c.strip()) > 0, f"{fn}: 空命令")

    def test_device_tags_are_real_names(self):
        """设备标记应该是 sw1/sw2/PICOS/PICOS-OVS 等，不是 pica,N"""
        for fn, steps in self.data.items():
            for c in all_cmds(steps):
                if c.startswith('>>>'):
                    self.assertNotIn('pica,', c, f"{fn}: {c}")


# ============================================================
# 1. pica8QOSFunc_04_01.txt.txt
# ============================================================
class TestQOS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = ScriptParser.parse_steps(load('pica8QOSFunc_04_01.txt.txt'))
    def test_step_count(self):
        self.assertEqual(len(self.steps), 8)
    def test_init(self):
        self.assertEqual(self.steps[0][0], '\u521d\u59cb\u5316 (Step \u4e4b\u524d)')
    def test_step1_cmds(self):
        for n, l in self.steps:
            if 'Step 1' in n:
                cmds = ScriptParser.extract_commands(l)
                self.assertIn('set vlans vlan-id 199', cmds)
                for c in cmds:
                    if c.startswith('>>>') or c == 'commit': continue
                    self.assertNotIn(' ative-vlan-id', c)
                break
    def test_packets(self):
        self.assertEqual(sum(len(ScriptParser.extract_packets(l)) for _, l in self.steps), 4)
    def test_total(self):
        self.assertEqual(len(all_cmds(self.steps)), 34)
    def test_device_tag(self):
        self.assertEqual(steps_missing_tag(self.steps), 0)


# ============================================================
# 2. pica8FdbFunc_01_24.txt
# ============================================================
class TestFDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = ScriptParser.parse_steps(load('pica8FdbFunc_01_24.txt'))
    def test_step_count(self):
        self.assertEqual(len(self.steps), 7)
    def test_step1(self):
        for n, l in self.steps:
            if 'Step 1' in n:
                cmds = ScriptParser.extract_commands(l)
                self.assertIn('run clear mac-address table all', cmds)
                break
    def test_packets(self):
        self.assertEqual(sum(len(ScriptParser.extract_packets(l)) for _, l in self.steps), 1)
    def test_total(self):
        self.assertEqual(len(all_cmds(self.steps)), 18)
    def test_device_tag(self):
        self.assertEqual(steps_missing_tag(self.steps), 0)


# ============================================================
# 3. pica8SysFunc_12_01.txt.txt
# ============================================================
class TestSys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = ScriptParser.parse_steps(load('pica8SysFunc_12_01.txt.txt'))
    def test_sub_steps(self):
        names = [s[0] for s in self.steps]
        self.assertTrue(any('3.1' in n for n in names))
    def test_init_has_cmds(self):
        self.assertGreater(len(ScriptParser.extract_commands(self.steps[0][1])), 0)
    def test_total(self):
        self.assertEqual(len(all_cmds(self.steps)), 33)
    def test_device_tag(self):
        self.assertEqual(steps_missing_tag(self.steps), 0)


# ============================================================
# 4. pica8OvsGroupEcmpSelect_11.txt
# ============================================================
class TestOVSEcmp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = ScriptParser.parse_steps(load('pica8OvsGroupEcmpSelect_11.txt'))
    def test_step_count(self):
        self.assertEqual(len(self.steps), 4)
    def test_ovs_cmds(self):
        self.assertTrue(any('ovs-' in c for c in all_cmds(self.steps)))
    def test_multiline_not_truncated(self):
        for c in all_cmds(self.steps):
            if c.startswith('ovs-vsctl add-port'):
                self.assertIn('type=pica8', c)
    def test_packets(self):
        self.assertEqual(sum(len(ScriptParser.extract_packets(l)) for _, l in self.steps), 2)
    def test_total(self):
        self.assertEqual(len(all_cmds(self.steps)), 38)
    def test_device_tag(self):
        self.assertEqual(steps_missing_tag(self.steps), 0)


# ============================================================
# 5. pica8OvsGroupSelect_03.txt
# ============================================================
class TestOVSSelect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = ScriptParser.parse_steps(load('pica8OvsGroupSelect_03.txt'))
    def test_step_count(self):
        self.assertEqual(len(self.steps), 16)
    def test_sub_steps(self):
        names = [s[0] for s in self.steps]
        self.assertTrue(any('1.1' in n for n in names))
        self.assertTrue(any('10.1' in n for n in names))
    def test_packets(self):
        self.assertEqual(sum(len(ScriptParser.extract_packets(l)) for _, l in self.steps), 10)
    def test_total(self):
        self.assertEqual(len(all_cmds(self.steps)), 88)
    def test_device_tag(self):
        self.assertEqual(steps_missing_tag(self.steps), 0)


# ============================================================
# 6. pica8LoadBalanceVrrpV3Func_01_01.txt
# ============================================================
class TestLoadBalance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = ScriptParser.parse_steps(load('pica8LoadBalanceVrrpV3Func_01_01.txt'))
        cls.cmds = all_cmds(cls.steps)
    def test_step_count(self):
        self.assertEqual(len(self.steps), 56)
    def test_sub_steps(self):
        names = [s[0] for s in self.steps]
        self.assertTrue(any('8.1' in n for n in names))
    def test_device_tag_in_init(self):
        cmds = ScriptParser.extract_commands(self.steps[0][1])
        tags = [c for c in cmds if c.startswith('>>>')]
        self.assertTrue(any('sw1' in t for t in tags))
    def test_step1_has_device_tag(self):
        """Step 1 必须有设备标记"""
        for n, l in self.steps:
            if n.startswith('Step 1:'):
                cmds = ScriptParser.extract_commands(l)
                self.assertTrue(any(c.startswith('>>>') for c in cmds), f"Step 1 无设备标记: {cmds[:3]}")
                break
    def test_commit_extracted(self):
        self.assertGreater(sum(1 for c in self.cmds if c == 'commit'), 0)
    def test_commit_not_dedup(self):
        for n, l in self.steps:
            if n.startswith('Step 1:'):
                cmds = ScriptParser.extract_commands(l)
                self.assertGreater(sum(1 for c in cmds if c == 'commit'), 1)
                break
    def test_no_unresolved(self):
        self.assertFalse(has_unresolved(self.cmds))
    def test_device_tag(self):
        self.assertEqual(steps_missing_tag(self.steps), 0)
    def test_total(self):
        self.assertEqual(len(self.cmds), 1702)


# ============================================================
# 7. bgpv6vrffun_03.txt
# ============================================================
class TestBGP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = ScriptParser.parse_steps(load('bgpv6vrffun_03.txt'))
        cls.cmds = all_cmds(cls.steps)
    def test_step_count(self):
        self.assertEqual(len(self.steps), 26)
    def test_has_sw1_sw2(self):
        tags = ' '.join(c for c in self.cmds if c.startswith('>>>'))
        self.assertIn('sw1', tags)
        self.assertIn('sw2', tags)
    def test_step1_has_dut_and_config(self):
        for n, l in self.steps:
            if n.startswith('Step 1:'):
                cmds = ScriptParser.extract_commands(l)
                self.assertTrue(any(c.startswith('>>>') for c in cmds))
                self.assertTrue(any(c.startswith('set ') for c in cmds))
                self.assertTrue(any(c == 'commit' for c in cmds))
                break
    def test_no_unresolved(self):
        self.assertFalse(has_unresolved(self.cmds))
    def test_device_tag(self):
        self.assertEqual(steps_missing_tag(self.steps), 0)
    def test_total(self):
        self.assertEqual(len(self.cmds), 340)


# ============================================================
# 8. pica8MlagMacSyncFunc_01_03.txt
# ============================================================
class TestMLAG03(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = ScriptParser.parse_steps(load('pica8MlagMacSyncFunc_01_03.txt'))
        cls.cmds = all_cmds(cls.steps)
    def test_step_count(self):
        self.assertEqual(len(self.steps), 21)
    def test_has_multiple_devices(self):
        tags = ' '.join(c for c in self.cmds if c.startswith('>>>'))
        self.assertIn('sw1', tags)
        self.assertIn('sw2', tags)
    def test_step0_sw4_has_cmds(self):
        """Step 0 中 sw4 应有配置命令（不只是 commit）"""
        for n, l in self.steps:
            if 'Step 0' in n and 'Init' in n:
                cmds = ScriptParser.extract_commands(l)
                # 找 sw4 标记后面的命令
                in_sw4 = False
                sw4_cmds = []
                for c in cmds:
                    if '>>> [sw4]' in c:
                        in_sw4 = True
                        continue
                    if c.startswith('>>>'):
                        in_sw4 = False
                    if in_sw4 and c != 'commit':
                        sw4_cmds.append(c)
                self.assertGreater(len(sw4_cmds), 0, f"sw4 应有配置命令: {cmds}")
                break
    def test_step1_multi_device(self):
        for n, l in self.steps:
            if n.startswith('Step 1:'):
                cmds = ScriptParser.extract_commands(l)
                tags = [c for c in cmds if c.startswith('>>>')]
                self.assertGreater(len(tags), 1)
                break
    def test_packets(self):
        self.assertEqual(sum(len(ScriptParser.extract_packets(l)) for _, l in self.steps), 2)
    def test_device_tag(self):
        self.assertEqual(steps_missing_tag(self.steps), 0)
    def test_total(self):
        self.assertEqual(len(self.cmds), 485)


# ============================================================
# 9. pica8MlagMacSyncFunc_01_11.txt
# ============================================================
class TestMLAG11(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = ScriptParser.parse_steps(load('pica8MlagMacSyncFunc_01_11.txt'))
        cls.cmds = all_cmds(cls.steps)
    def test_step_count(self):
        self.assertEqual(len(self.steps), 34)
    def test_sub_steps(self):
        names = [s[0] for s in self.steps]
        self.assertTrue(any('2.1' in n for n in names))
        self.assertTrue(any('16.2' in n for n in names))
    def test_has_multiple_devices(self):
        tags = ' '.join(c for c in self.cmds if c.startswith('>>>'))
        self.assertIn('sw1', tags)
        self.assertIn('sw2', tags)
    def test_packets(self):
        self.assertEqual(sum(len(ScriptParser.extract_packets(l)) for _, l in self.steps), 2)
    def test_device_tag(self):
        self.assertEqual(steps_missing_tag(self.steps), 0)
    def test_total(self):
        self.assertEqual(len(self.cmds), 684)


# ============================================================
# 边界情况
# ============================================================
class TestEdgeCases(unittest.TestCase):
    def test_empty(self):
        for _, l in ScriptParser.parse_steps(""):
            self.assertEqual(len(ScriptParser.extract_commands(l)), 0)

    def test_no_step(self):
        text = '#Proc -- send_expect {set vlans vlan-id 100}\nadmin@PICOS# set vlans vlan-id 100\nadmin@PICOS#\n'
        steps = ScriptParser.parse_steps(text)
        self.assertEqual(steps[0][0], '\u5168\u90e8\u5185\u5bb9')

    def test_line_wrap_fix(self):
        lines = [
            '#Proc -- send_expect {set class-of-service scheduler-profile p1 forwarding-class f1 scheduler s1}',
            'admin@PICOS# set class-of-service scheduler-profile p1 forwarding-class f1 sched uler s1',
            'admin@PICOS#',
        ]
        cmds = ScriptParser.extract_commands(lines)
        self.assertNotIn('sched uler', cmds[-1])
        self.assertIn('scheduler', cmds[-1])

    def test_variable_replacement(self):
        lines = [
            '#Proc -- send_expect {set interface gigabit-ethernet $Dut1P2 family ethernet-switching native-vlan-id 100}',
            'admin@PICOS# set interface gigabit-ethernet xe-1/1/2 family ethernet-switching native-vlan-id 100',
            'admin@PICOS#',
        ]
        cmds = ScriptParser.extract_commands(lines)
        cmd = [c for c in cmds if not c.startswith('>>>')][0]
        self.assertIn('xe-1/1/2', cmd)
        self.assertNotIn('Dut1P2', cmd)

    def test_ovs_prompt(self):
        lines = [
            '#Proc -- send_expect {ovs-vsctl add-br br0}',
            '[?2004hadmin@PICOS-OVS:~$ ovs-vsctl add-br br0',
            '[?2004hadmin@PICOS-OVS:~$',
        ]
        cmds = ScriptParser.extract_commands(lines)
        real = [c for c in cmds if not c.startswith('>>>')]
        self.assertIn('ovs-vsctl add-br br0', real[0])

    def test_pcap_magic(self):
        pkt = bytes.fromhex('001122334455667788990011080045000028')
        pcap = ScriptParser.packets_to_pcap([pkt])
        self.assertTrue(pcap.startswith(b'\xd4\xc3\xb2\xa1'))

    def test_bare_commit(self):
        lines = [
            '#Proc -- send_expect {set vlans vlan-id 11}',
            'admin@sw1# set vlans vlan-id 11', 'admin@sw1#',
            '#Proc -- send_expect commit',
            'admin@sw1# commit', 'admin@sw1#',
        ]
        cmds = ScriptParser.extract_commands(lines)
        self.assertIn('commit', cmds)

    def test_commit_empty_braces(self):
        lines = ['#Proc -- send_expect commit {} -notry true', 'admin@sw1# commit', 'admin@sw1#']
        self.assertIn('commit', ScriptParser.extract_commands(lines))

    def test_dut_tag_uses_device_name(self):
        lines = [
            '#Proc -- dut_reconnect pica,1', 'admin@sw1#',
            '#Proc -- send_expect {set vlans vlan-id 11}',
            'admin@sw1# set vlans vlan-id 11', 'admin@sw1#',
            '#Proc -- dut_reconnect pica,2', 'admin@sw2#',
            '#Proc -- send_expect {set vlans vlan-id 22}',
            'admin@sw2# set vlans vlan-id 22', 'admin@sw2#',
        ]
        cmds = ScriptParser.extract_commands(lines)
        tags = [c for c in cmds if c.startswith('>>>')]
        self.assertIn('>>> [sw1] <<<', tags)
        self.assertIn('>>> [sw2] <<<', tags)

    def test_dup_dut_collapsed(self):
        lines = [
            '#Proc -- dut_reconnect pica,1', 'admin@sw1#',
            '#Proc -- dut_reconnect pica,1', 'admin@sw1#',
            '#Proc -- send_expect {set vlans vlan-id 11}',
            'admin@sw1# set vlans vlan-id 11', 'admin@sw1#',
        ]
        cmds = ScriptParser.extract_commands(lines)
        tags = [c for c in cmds if c.startswith('>>>')]
        self.assertEqual(len(tags), 1)

    def test_device_switch_clears_dedup(self):
        """切换设备后，相同命令应该再次出现"""
        lines = [
            '#Proc -- dut_reconnect pica,1', 'admin@sw1#',
            '#Proc -- send_expect {set vlans vlan-id 100}',
            'admin@sw1# set vlans vlan-id 100', 'admin@sw1#',
            '#Proc -- dut_reconnect pica,2', 'admin@sw2#',
            '#Proc -- send_expect {set vlans vlan-id 100}',
            'admin@sw2# set vlans vlan-id 100', 'admin@sw2#',
        ]
        cmds = ScriptParser.extract_commands(lines)
        vlan_cmds = [c for c in cmds if c == 'set vlans vlan-id 100']
        self.assertEqual(len(vlan_cmds), 2, f"相同命令在不同设备应出现两次: {cmds}")

    def test_no_dut_reconnect_uses_prompt(self):
        """没有 dut_reconnect 时，从提示符推断设备"""
        lines = [
            'admin@sw3#',
            '#Proc -- send_expect {set vlans vlan-id 100}',
            'admin@sw3# set vlans vlan-id 100', 'admin@sw3#',
        ]
        cmds = ScriptParser.extract_commands(lines)
        tags = [c for c in cmds if c.startswith('>>>')]
        self.assertGreater(len(tags), 0, f"应从提示符推断设备: {cmds}")
        self.assertIn('sw3', tags[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
