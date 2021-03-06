"""
Tests that test voltron in the lldb cli driver

Tests:
Client -> Server -> LLDBAdaptor

Inside an LLDB CLI driver instance
"""

import tempfile
import sys
import json
import time
import logging
import pexpect
import os

from mock import Mock
from nose.tools import *

import voltron
from voltron.core import *
from voltron.api import *
from voltron.plugin import PluginManager, DebuggerAdaptorPlugin

from common import *

log = logging.getLogger('tests')

p = None
client = None

def setup():
    global p, client, pm

    log.info("setting up LLDB CLI tests")

    voltron.setup_env()

    # compile test inferior
    pexpect.run("cc -o tests/inferior tests/inferior.c")

    # start debugger
    start_debugger()
    time.sleep(1)

def teardown():
    read_data()
    p.terminate(True)
    time.sleep(2)

def start_debugger(do_break=True):
    global p, client
    p = pexpect.spawn('lldb')
    p.sendline("settings set target.x86-disassembly-flavor intel")
    p.sendline("command script import dbgentry.py")
    p.sendline("file tests/inferior")
    p.sendline("voltron init")
    p.sendline("process kill")
    p.sendline("break delete 1")
    if do_break:
        p.sendline("b main")
    p.sendline("run loop")
    read_data()
    client = Client()
    client.connect()

def stop_debugger():
    p.terminate(True)

def read_data():
    try:
        while True:
            p.read_nonblocking(size=64, timeout=1)
    except:
        pass

def restart_debugger(do_break=True):
    stop_debugger()
    start_debugger(do_break)

def test_bad_request():
    req = client.create_request('version')
    req.request = 'xxx'
    res = client.send_request(req)
    assert res.is_error
    assert res.code == 0x1002

def test_version():
    req = client.create_request('version')
    res = client.send_request(req)
    assert res.api_version == 1.0
    assert 'lldb' in res.host_version

def test_registers():
    global registers
    restart_debugger()
    time.sleep(1)
    read_data()
    res = client.perform_request('registers')
    registers = res.registers
    assert res.status == 'success'
    assert len(registers) > 0
    assert registers['rip'] != 0

def test_memory():
    restart_debugger()
    time.sleep(1)
    res = client.perform_request('memory', address=registers['rip'], length=0x40)
    assert res.status == 'success'
    assert len(res.memory) > 0

def test_state_stopped():
    restart_debugger()
    time.sleep(1)
    res = client.perform_request('state')
    assert res.is_success
    assert res.state == "stopped"

def test_wait_timeout():
    restart_debugger()
    time.sleep(1)
    res = client.perform_request('wait', timeout=2)
    assert res.is_error
    assert res.code == 0x1004

def test_targets():
    restart_debugger()
    time.sleep(1)
    res = client.perform_request('targets')
    assert res.is_success
    assert res.targets[0]['state'] == "stopped"
    assert res.targets[0]['arch'] == "x86_64"
    assert res.targets[0]['id'] == 0
    assert res.targets[0]['file'].endswith('tests/inferior')

def test_stack():
    restart_debugger()
    time.sleep(1)
    res = client.perform_request('stack', length=0x40)
    assert res.status == 'success'
    assert len(res.memory) > 0

def test_command():
    restart_debugger()
    time.sleep(1)
    res = client.perform_request('command', command="reg read")
    assert res.status == 'success'
    assert len(res.output) > 0
    assert 'rax' in res.output

def test_disassemble():
    restart_debugger()
    time.sleep(1)
    res = client.perform_request('disassemble', count=0x20)
    assert res.status == 'success'
    assert len(res.disassembly) > 0
    assert 'push' in res.disassembly

def test_dereference():
    restart_debugger()
    time.sleep(1)
    res = client.perform_request('registers')
    res = client.perform_request('dereference', pointer=res.registers['rsp'])
    assert res.status == 'success'
    assert res.output[0][0] == 'pointer'
    assert res.output[-1][1] == 'start + 0x1'

def test_breakpoints():
    restart_debugger()
    time.sleep(1)
    res = client.perform_request('breakpoints')
    assert res.status == 'success'
    assert len(res.breakpoints) == 1
    assert res.breakpoints[0]['one_shot'] == False
    assert res.breakpoints[0]['enabled']
    assert res.breakpoints[0]['id'] == 1
    assert res.breakpoints[0]['hit_count'] > 0
    assert res.breakpoints[0]['locations'][0]['name'] == "inferior`main"
