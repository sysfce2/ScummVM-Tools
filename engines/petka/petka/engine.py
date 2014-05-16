# -*- coding: utf-8 -*-

# romiq.kh@gmail.com, 2014

import os
import struct
import io

from .fman import FileManager
from . import EngineError

OPCODES = {
    1:  ("USE",         0),
    2:  ("SETPOS",      2),
    3:  ("GOTO",        0),
    4:  ("LOOK",        0),
    5:  ("SAY",         0),
    6:  ("TAKE",        0),
    9:  ("WALK",        2),
    10: ("TALK",        0),
    11: ("END",         0),
    14: ("SET",         1),
    15: ("SHOW",        1),
    16: ("HIDE",        0),
    17: ("DIALOG",      1),
    18: ("ZBUFFER",     0),
    19: ("TOTALINIT",   1),
    20: ("ANIMATE",     1),
    21: ("STATUS",      1),
    22: ("ADDINV",      0),
    23: ("DELINV",      0),
    24: ("STOP",        1),
    25: ("CURSOR",      1),
    26: ("OBJECTUSE",   0),
    27: ("ACTIVE",      1),
    28: ("SAID",        0),
    29: ("SETSEQ",      0),
    30: ("ENDSEQ",      0),
    31: ("CHECK",       0),
    32: ("IF",          0),
    33: ("DESCRIPTION", 0),
    34: ("HALF",        0),
    36: ("WALKTO",      0),
    37: ("WALKVICH",    0),
    38: ("INITBG",      0),
    39: ("USERMSG",     0),
    40: ("SYSTEM",      0),
    41: ("SETZBUFFER",  0),
    42: ("CONTINUE",    0),
    43: ("MAP",         1),
    44: ("PASSIVE",     1),
    45: ("NOMAP",       1),
    46: ("SETINV",      1),
    47: ("BGSFX",       1),
    48: ("MUSIC",       1),
    49: ("IMAGE",       1),
    50: ("STAND",       1),
    51: ("ON",          1),
    52: ("OFF",         1),
    53: ("PLAY",        1),
    54: ("LEAVEBG",     0),
    55: ("SHAKE",       1),
    56: ("SP",          2),
    57: ("RANDOM",      1),
    58: ("JUMP",        0),
    59: ("JUMPVICH",    0),
    60: ("PART",        2),
    61: ("CHAPTER",     2),
    62: ("AVI",         1),
    63: ("TOMAP",       0),
}

class ScrObject:
    def __init__(self, idx, name):
        self.idx = idx
        self.name = name
        self.acts = None

class MsgObject:
    def __init__(self, idx, wav, arg1, arg2, arg3):
        self.idx = idx
        self.wav = wav
        self.arg1 = arg1
        self.arg2 = arg2
        self.arg3 = arg3
        self.name = None

class DlgGrpObject:
    def __init__(self, idx, num_acts, arg1):
        self.idx = idx
        self.num_acts = num_acts
        self.arg1 = arg1
        self.acts = None

class DlgActObject:
    def __init__(self, num_dlgs, opcode, ref, arg1, arg2):
        self.num_dlgs = num_dlgs
        self.opcode = opcode
        self.ref = ref
        self.arg1 = arg1
        self.arg2 = arg2
        self.dlgs = None
        self.obj = None

class DlgObject:
    def __init__(self, op_start, arg1, arg2):
        self.op_start = op_start
        self.arg1 = arg1
        self.arg2 = arg2
        self.ops = None

class DlgOpObject:
    def __init__(self, opcode, arg, ref):
        self.opcode = opcode
        self.arg = arg
        self.ref = ref
        self.msg = None
        
class Engine:
    def __init__(self):
        self.fman = None
        self.parts = []
        self.start_part = None
        self.start_chap = None
        self.start_scene = None

        self.curr_part = None
        self.curr_chap = None
        
        self.curr_path = None
        self.curr_speech = None
        self.curr_diskid = None
        
        
    def parse_ini(self, f):
        # parse ini settings
        curr_sect = None
        ini = {}
        order_sect = []
        orders = {}
        for line in f.readlines():
            line = line.decode(self.enc).strip()
            if len(line) == 0: continue
            if line[:1] == ";": continue
            if line[:1] == "[" and line[-1:] == "]":
                if curr_sect is not None:
                    orders[curr_sect] = order
                curr_sect = line[1:-1].strip()
                order_sect.append(curr_sect)
                order = []
                ini[curr_sect] = {}
                continue
            kv = line.split("=", 1)
            if len(kv) != 2: continue
            ini[curr_sect][kv[0].strip()] = kv[1].strip()
            order.append(kv[0].strip())
        orders[curr_sect] = order
        ini["__ordersect__"] = order_sect
        ini["__order__"] = orders
        return ini
        
    def parse_res(self, f):
        res  = {}
        resord = []
        for line in f.readlines():
            line = line.decode(self.enc).strip()
            if len(line) == 0:
                continue
            pair = line.split("=", 1)
            if len(pair) < 2:
                continue
            value = pair[1].strip()
            if value[:1] == "=":
                value = value[1:].strip()
            res_id = int(pair[0].strip(), 10)
            res[res_id] = value
            resord.append(res_id)
        return res, resord
        
    def load_data(self, folder, enc):
        self.fman = FileManager(folder)
        self.enc = enc
        # load PARTS.INI
        pf = self.fman.find_path("parts.ini")
        if pf:
            f = open(pf, "rb")
            try:
                self.parts_ini = self.parse_ini(f)
            finally:
                f.close()
            for sect in self.parts_ini["__ordersect__"]:
                data = self.parts_ini[sect]
                if sect == "All":
                    if "Part" in data:
                        self.start_part = int(data["Part"])
                    if "Chapter" in data:
                        self.start_chap = int(data["Chapter"])
                elif sect[:5] == "Part ":
                    self.parts.append(sect)
        else:
            # load BGS.INI only (e.g. DEMO)
            self.parts_ini = None
            
        # std stores
        self.fman.load_store("patch.str")
        self.fman.load_store("main.str")

    def open_part(self, part, chap):
        self.fman.unload_stores(1)
        self.curr_part = part
        self.curr_chap = chap
        if self.parts_ini:
            pname = "Part {}".format(part)
            pcname = pname
            if chap:
                pcname += " Chapter {}".format(chap)
            ini = self.parts_ini[pname]
            self.curr_path = ini["CurrentPath"]
            self.curr_speech = ini["PathSpeech"]
            self.curr_diskid = ini["DiskID"]
            inic = self.parts_ini[pcname]
            if "Chapter" in inic:
                self.fman.load_store(inic["Chapter"], 1)
        else:
            ini = {}
            self.curr_path = ""
            self.curr_speech = ""
            self.curr_diskid = None
        
        # load BGS.INI
        self.bgs_ini = {}
        self.start_scene = None
        pf = self.fman.find_path(self.curr_path + "bgs.ini")
        if pf:
            f = open(pf, "rb")
            try:
                self.bgs_ini = self.parse_ini(f)
            finally:
                f.close()
            if "Settings" in self.bgs_ini:
                if "StartRoom" in self.bgs_ini["Settings"]:
                    self.start_scene = self.bgs_ini["Settings"]["StartRoom"]
        # load .STR
        strs = ["Flics", "Background", "Wav", "Music", "SFX"]
        for strf in strs:
            pf = self.fman.find_path(self.curr_path + "bgs.ini")
            if not pf: continue
            if strf in ini:
                self.fman.load_store(ini[strf], 1)
        # load script.dat, backgrnd.bg and resources.qrc
        self.load_script()
        # load names & invntr
        self.load_names()
        # load dialogs
        self.load_dialogs()
        
    def load_script(self):
        self.objects = []
        self.scenes = []
        self.obj_idx = {}
        self.scn_idx = {}

        try:
            data = self.fman.read_file(self.curr_path + "script.dat")
        except:
            raise EngineError("Can't open SCRIPT.DAT")
        num_obj, num_scn = struct.unpack_from("<II", data[:8])
        off = 8
        def read_rec(off):
            obj_id, name_len = struct.unpack_from("<HI", data[off:off + 6])
            off += 6
            name = data[off:off + name_len].decode(self.enc)
            off += name_len
            num_act = struct.unpack_from("<I", data[off:off + 4])[0]
            off += 4
            acts = []
            for i in range(num_act):
                act_id, act_cond, act_arg, num_op = struct.unpack_from(\
                    "<HBHI", data[off:off + 9])
                off += 9
                ops = []
                for j in range(num_op):
                    op = struct.unpack_from("<5H", data[off:off + 10])
                    off += 10
                    ops.append(op)
                acts.append([act_id, act_cond, act_arg, ops])
            rec = ScrObject(obj_id, name)
            rec.acts = acts
            return off, rec
        
        for i in range(num_obj):
            off, obj = read_rec(off)
            self.objects.append(obj)
            self.obj_idx[obj.idx] = obj

        for i in range(num_scn):
            off, scn = read_rec(off)
            self.scenes.append(scn)
            self.scn_idx[scn.idx] = scn
            
        data = self.fman.read_file(self.curr_path + "backgrnd.bg")
        num_rec = struct.unpack_from("<I", data[:4])[0]
        off = 4
        for i in range(num_rec):
            scn_ref, num_ref = struct.unpack_from("<HI", data[off:off + 6])
            off += 6
            if scn_ref in self.scn_idx:
                scn = self.scn_idx[scn_ref]    
                scn.refs = []
            else:
                raise EngineError("DEBUG: Scene ID = 0x{:x} not found".\
                    format(scn_ref))

            for j in range(num_ref):
                ref = struct.unpack_from("<H5I", data[off:off + 22])
                off += 22
                if ref[0] in self.obj_idx:
                    obj = self.obj_idx[ref[0]]
                    scn.refs.append([obj] + list(ref[1:]))
                else:
                    raise EngineError("DEBUG: Scene ref 0x{:x} not found".\
                        format(obj[0]))
                        
        f = self.fman.read_file_stream(self.curr_path + "resource.qrc")
        self.res, self.resord = self.parse_res(f)
        f.close()
        
    def load_names(self):
        self.names = {}
        self.namesord = []
        fp = self.curr_path + "names.ini"
        if self.fman.exists(fp):
            f = self.fman.read_file_stream(fp)
            ini = self.parse_ini(f)
            self.names = ini["all"]
            self.namesord = ini["__order__"]["all"]
            f.close()

        self.invntr = {}
        self.invntrord = []
        fp = self.curr_path + "invntr.txt"
        if self.fman.exists(fp):
            f = self.fman.read_file_stream(fp)
            ini = self.parse_ini(f)
            self.invntr = ini["ALL"]
            self.invntrord = ini["__order__"]["ALL"]
            f.close()
        
    def load_dialogs(self):
        self.msgs = []
        # DIALOGUES.LOD
        fp = self.curr_path + "dialogue.lod"
        if self.fman.exists(fp):
            f = self.fman.read_file_stream(fp)
            try:
                temp = f.read(4)
                num_msg = struct.unpack_from("<I", temp)[0]
                for i in range(num_msg):
                    temp = f.read(24)
                    arg1, wav, arg2, arg3 = struct.unpack_from("<I12sII", temp)
                    msg = MsgObject(len(self.msgs), \
                        wav.decode(self.enc).strip(), arg1, arg2, arg3)
                    # scan objects
                    msg.obj = self.obj_idx.get(arg1, None)
                    if not msg.obj:
                        raise EngineError("DEBUG: Message ref = 0x{:x} not found".\
                        format(obj[0]))
                    self.msgs.append(msg)
                for i, capt in enumerate(f.read().split(b"\x00")):
                    if i < len(self.msgs):
                        self.msgs[i].name = capt.decode(self.enc)
            finally:
                f.close()

        self.dlgs = []
        self.dlgops = []
        # DIALOGUES.FIX
        fp = self.curr_path + "dialogue.fix"
        if self.fman.exists(fp):
            f = self.fman.read_file_stream(fp)
            try:
                temp = f.read(4)
                num_grps = struct.unpack_from("<I", temp)[0]
                for i in range(num_grps):
                    temp = f.read(12)
                    idx, num_acts, arg1 = struct.unpack_from("<III", temp)
                    grp = DlgGrpObject(idx, num_acts, arg1)
                    self.dlgs.append(grp)
                opref = {}
                for grp in self.dlgs:
                    grp.acts = []
                    for i in range(grp.num_acts):
                        temp = f.read(16)
                        opcode, ref, num_dlgs, arg1, arg2 = \
                            struct.unpack_from("<2H3I", temp)
                        act = DlgActObject(num_dlgs, opcode, ref, arg1, arg2)
                        if ref not in self.obj_idx:
                            raise EngineError("Dialog group 0x{:x} refered "\
                                "to unexisted object 0x{:x}".format(grp.idx, ref))
                        act.obj = self.obj_idx[act.ref]
                        grp.acts.append(act)
                    for act in grp.acts:
                        act.dlgs = []
                        for i in range(act.num_dlgs):
                            temp = f.read(12)
                            op_start, arg1, arg2 = \
                                struct.unpack_from("<3I", temp)
                            if op_start in opref:
                                raise EngineError(
                                    "Multiple dialog opcodes reference")
                            dlg = DlgObject(op_start, arg1, arg2)
                            opref[op_start] = dlg
                            dlg.ops = None
                            act.dlgs.append(dlg)
                temp = f.read(4)
                num_ops = struct.unpack_from("<I", temp)[0]
                for i in range(num_ops):
                    temp = f.read(4)
                    ref, arg, code  = struct.unpack_from("<HBB", temp)
                    dlgop = DlgOpObject(code, arg, ref)
                    if ref < len(self.msgs):
                        dlgop.msg = self.msgs[ref]
                    self.dlgops.append(dlgop)
                dlg = None
                oparr = []
                for idx, oprec in enumerate(self.dlgops):
                    if idx in opref:
                        if len(oparr) > 0:
                            dlg.ops = oparr
                            oparr = []
                        dlg = opref[idx]
                    oparr.append(oprec)    
                if len(oparr) > 0:
                    dlg.ops = oparr
            finally:
                f.close()
