#!/usr/bin/env python3
"""SpaceBourne 2 Save Editor  (Español / English)
Editor basico de guardados (Unreal Engine 4.27 + Rama Save). Solo usa la libreria estandar de Python.

- Busca los guardados en %LOCALAPPDATA%\\SB2\\Saved\\SaveGames
- Suma dinero (500k / 3M) y experiencia de piloto, soldado y explorador (100k / 1M)
- Fija el nivel de cada area; al SUBIR de nivel suma PUNTOS_POR_NIVEL puntos de atributo por cada nivel ganado
- Anade naves al guardado (plantillas en sb2_ships_catalog.json, junto a este archivo o dentro del .exe)
- Interfaz en espanol e ingles, con un boton para cambiar de idioma
- Antes de escribir hace una copia en %LOCALAPPDATA%\\SB2\\SaveEditor_Backups
CIERRA EL JUEGO antes de guardar cambios.
"""
import base64
import json
import os
import random
import re
import shutil
import struct
import sys
import time
import zlib

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # permite usar el nucleo sin interfaz
    tk = None

# ----------------------------------------------------------------------------
# Nucleo: formato del guardado
# ----------------------------------------------------------------------------
TAG = 0x9E2A83C1
BLOCK = 0x20000          # 128 KB por bloque
INT_MAX = 2_147_483_647  # los valores son enteros de 32 bits
PUNTOS_POR_NIVEL = 3     # puntos de atributo que se suman por cada nivel ganado
MAX_NIVEL = 99           # tope del editor (el maximo real del juego no se conoce)

TIPOS = {  # clave: (nombre visible, campo de XP, campo de nivel, campo de puntos de atributo)
    'piloto': ('Piloto', 'PILOT_CurrentExp', 'PILOT_Level', 'PILOT_AttributePoints'),
    'soldado': ('Soldado', 'CHAR_CurrentExp', 'CHAR_Level', 'CHAR_AttributePoints'),
    'explorador': ('Explorador', 'ADV_CurrentExp', 'ADV_Level', 'ADV_AttributePoinst'),  # asi lo escribe el juego
}


def decompress(raw: bytes) -> bytes:
    pos, out = 0, bytearray()
    while pos < len(raw):
        tag, _chunk = struct.unpack_from('<qq', raw, pos)
        if tag != TAG:
            raise ValueError('Not a SpaceBourne 2 save (invalid header). / No es un guardado de SpaceBourne 2 (cabecera inválida).')
        pos += 16
        _sc, su = struct.unpack_from('<qq', raw, pos)
        pos += 16
        infos, tot = [], 0
        while tot < su:
            c, u = struct.unpack_from('<qq', raw, pos)
            pos += 16
            infos.append((c, u))
            tot += u
        for c, _u in infos:
            out += zlib.decompress(raw[pos:pos + c])
            pos += c
    return bytes(out)


def compress(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), BLOCK):
        chunk = data[i:i + BLOCK]
        z = zlib.compress(chunk, 6)
        out += struct.pack('<qq', TAG, BLOCK)
        out += struct.pack('<qq', len(z), len(chunk))
        out += struct.pack('<qq', len(z), len(chunk))
        out += z
    return bytes(out)


def money_offset(data: bytes) -> int:
    key = struct.pack('<i', 12) + b'PlayerMoney\x00'
    occ = [m.start() for m in re.finditer(re.escape(key), data)]
    if not occ:
        raise ValueError('Money not found in this file. / No se encontró el dinero en este archivo.')
    o = occ[-1] + len(key)
    off = struct.unpack_from('<q', data, o)[0]
    if off != o + 8:
        raise ValueError('Unexpected money format. / Formato del dinero inesperado.')
    return off


def int_prop_offset(data: bytes, base: str) -> int:
    start = data.find(struct.pack('<i', 14) + b'CharacterData\x00', 100000)
    if start < 0:
        raise ValueError('Character data not found. / No se encontraron los datos del personaje.')
    m = re.compile(rb'..\x00\x00' + re.escape(base.encode()) + rb'_\d+_[0-9A-F]{32}\x00', re.S).search(data, start)
    if not m:
        raise ValueError(f'Field {base} not found. / No se encontró el campo {base}.')
    p = m.start()
    p += 4 + struct.unpack_from('<i', data, p)[0]
    n = struct.unpack_from('<i', data, p)[0]
    if data[p + 4:p + 4 + n - 1] != b'IntProperty':
        raise ValueError(f'Unexpected type in {base}. / Tipo inesperado en {base}.')
    return p + 4 + n + 8 + 1


# ----------------------------------------------------------------------------
# Naves (lista PlayersShips)
# ----------------------------------------------------------------------------
CATALOG_FILE = 'sb2_ships_catalog.json'
# Donde aparecen las naves nuevas: la estacion del Freelancers Guild en el sistema N25 (Oblivrax).
# Su nombre es fijo (no depende del nombre que el jugador ponga a sus propias estaciones).
GUILD_SOLAR = 'N25'
GUILD_STATION = 'Freelancers Guild'
TIER_MIN, TIER_MAX = 1, 4

# Nombres con los que el editor muestra cada clase de nave (son descripciones nuestras, no nombres oficiales).
# Si aparece una clase que no esta aqui, se muestra con su nombre interno.
NOMBRES_NAVES = {
    'es': {
        'SR_FighterS': 'Caza SR básico', 'SR_FighterS1': 'Caza SR avanzado', 'STL2_Fighter': 'Caza STL-2',
        'Player_HeavyFighter': 'Caza pesado', 'Frontier': 'Frontier', 'Falron_Tank': 'Tanque Falron',
        'Morhra_Assasin': 'Asesino Morhra', 'MiningShip_T2': 'Nave minera',
        'P_Trade_T1': 'Carguero comercial I', 'P_Trade_T2': 'Carguero comercial II',
        'P_Trade_T3': 'Carguero comercial III', 'P_Trade_T4': 'Carguero comercial IV',
        'P_Trade_Type2': 'Carguero comercial (tipo 2)',
        'Player_SwarmCarrierT1': 'Portaenjambres I', 'Player_SwarmCarrier2': 'Portaenjambres II',
        'Player_SwarmCarrierT3': 'Portaenjambres III', 'Player_SwarmCarrierT4': 'Portaenjambres IV',
        'Player_MotherShip': 'Nave nodriza', 'WRA_Ship': 'Nave WRA',
    },
    'en': {
        'SR_FighterS': 'SR Fighter (basic)', 'SR_FighterS1': 'SR Fighter (advanced)', 'STL2_Fighter': 'STL-2 Fighter',
        'Player_HeavyFighter': 'Heavy Fighter', 'Frontier': 'Frontier', 'Falron_Tank': 'Falron Tank',
        'Morhra_Assasin': 'Morhra Assassin', 'MiningShip_T2': 'Mining Ship',
        'P_Trade_T1': 'Trade Freighter I', 'P_Trade_T2': 'Trade Freighter II',
        'P_Trade_T3': 'Trade Freighter III', 'P_Trade_T4': 'Trade Freighter IV',
        'P_Trade_Type2': 'Trade Freighter (type 2)',
        'Player_SwarmCarrierT1': 'Swarm Carrier I', 'Player_SwarmCarrier2': 'Swarm Carrier II',
        'Player_SwarmCarrierT3': 'Swarm Carrier III', 'Player_SwarmCarrierT4': 'Swarm Carrier IV',
        'Player_MotherShip': 'Mothership', 'WRA_Ship': 'WRA Ship',
    },
}


def nombre_nave(clase, lang='es'):
    return NOMBRES_NAVES.get(lang, NOMBRES_NAVES['es']).get(clase, clase)

def fstr(d, p):
    n = struct.unpack_from('<i', d, p)[0]
    if n == 0: return '', p + 4
    if n < 0: return d[p+4:p+4-2*n-2].decode('utf-16le'), p + 4 - 2*n
    return d[p+4:p+4+n-1].decode('latin1'), p + 4 + n

def mkfstr(s):
    b = s.encode('latin1') + b'\0'
    return struct.pack('<i', len(b)) + b

def strip_guid(n): return re.sub(r'_\d+_[0-9A-F]{32}$', '', n)

def parse_struct(d, p):
    out = []
    while True:
        p0 = p
        name, p = fstr(d, p)
        if name == 'None': return out, p
        typ, p = fstr(d, p)
        size_pos = p
        size = struct.unpack_from('<q', d, p)[0]; p += 8
        extra = None
        if typ == 'StructProperty': extra, p = fstr(d, p); p += 16
        elif typ in ('ByteProperty', 'EnumProperty', 'ArrayProperty', 'SetProperty'): extra, p = fstr(d, p)
        elif typ == 'MapProperty':
            a, p = fstr(d, p); b, p = fstr(d, p); extra = (a, b)
        if typ == 'BoolProperty': p += 1
        p += 1
        out.append(dict(name=strip_guid(name), type=typ, extra=extra, val=p, size=size, start=p0, size_pos=size_pos))
        p += size

def read_ships(d):
    n = 'PlayersShips'; key = struct.pack('<i', len(n)+1) + n.encode() + b'\0'
    occ = [m.start() for m in re.finditer(re.escape(key), d)]
    if len(occ) < 2: raise ValueError('Ship list (PlayersShips) not found. / No se encontró la lista de naves (PlayersShips).')
    top = occ[1]
    q = top + len(key); ptr_pos = q; q += 8
    cnt_pos = q; count = struct.unpack_from('<i', d, q)[0]; q += 4
    _, q = fstr(d, q); _, q = fstr(d, q)
    size_pos = q; size = struct.unpack_from('<q', d, q)[0]; q += 8
    _, q = fstr(d, q); q += 16 + 1
    elems, p = [], q
    for _ in range(count):
        s = p; _, p = parse_struct(d, p); elems.append((s, p))
    if p - q != size or struct.unpack_from('<q', d, ptr_pos)[0] + 4 != p:
        raise ValueError('The ship list does not have the expected format. / La lista de naves no tiene el formato esperado.')
    return dict(ptr_pos=ptr_pos, cnt_pos=cnt_pos, count=count, size_pos=size_pos, end=p, elems=elems, first=q)

def ship_info(d, s, e):
    """clase, nombre, codigo, ubicacion y datos basicos de una nave d[s:e]"""
    props, _ = parse_struct(d, s)
    info = {}
    for pr in props:
        if pr['type'] == 'ObjectProperty': info['clase'] = fstr(d, pr['val'])[0].split('/')[-1].split('.')[0]
        if pr['name'] == 'Stats':
            sub, _ = parse_struct(d, pr['val'])
            for sp in sub:
                if sp['name'] in ('ShipName', 'ShipBarkot', 'DockedSolarID', 'DockedStationName'):
                    info[sp['name']] = fstr(d, sp['val'])[0]
                elif sp['name'] in ('ShipLevel', 'ShipTier'):
                    info[sp['name']] = struct.unpack_from('<i', d, sp['val'])[0]
                elif sp['name'] in ('PlayerOwnThatShip', 'PlayerPilotingThatShip'):
                    info[sp['name']] = bool(d[sp['val'] - 2])
    return info

# ---------- editar una nave (plantilla) con cambio de tamaños ----------
def customize(el, barcode, solar, station, tier=None, nivel=None):
    """devuelve los bytes de la nave con codigo unico, ubicacion y propiedad del jugador cambiados"""
    el = bytearray(el)
    props, _ = parse_struct(bytes(el), 0)
    stats = next(p for p in props if p['name'] == 'Stats')
    sub, _ = parse_struct(bytes(el), stats['val'])
    byname = {p['name']: p for p in sub}
    edits = []   # (inicio, fin, bytes_nuevos, pos_campo_tamano)
    def fs_edit(name, text):
        pr = byname[name]
        new = mkfstr(text)
        edits.append((pr['val'], pr['val'] + pr['size'], new, pr['size_pos']))
    fs_edit('ShipBarkot', barcode)
    if solar is not None:
        fs_edit('DockedSolarID', solar)
    if station is not None:
        fs_edit('DockedStationName', station)
    for nm, v in (('PlayerOwnThatShip', 1), ('PlayerPilotingThatShip', 0)):
        el[byname[nm]['val'] - 2] = v
    if tier is not None:
        struct.pack_into('<i', el, byname['ShipTier']['val'], int(tier))
    if nivel is not None:
        struct.pack_into('<i', el, byname['ShipLevel']['val'], int(nivel))
    total = 0
    for s, e, new, sp in sorted(edits, reverse=True):
        struct.pack_into('<q', el, sp, len(new))
        el[s:e] = new
        total += len(new) - (e - s)
    struct.pack_into('<q', el, stats['size_pos'], stats['size'] + total)
    return bytes(el)

# ---------- punteros absolutos del guardado ----------
def _isfs(d, p, maxlen=200):
    if p < 0 or p + 5 > len(d): return None
    n = struct.unpack_from('<i', d, p)[0]
    if 2 <= n <= maxlen and p + 4 + n <= len(d) and d[p+4+n-1] == 0:
        s = d[p+4:p+4+n-1]
        if all(32 <= c < 127 for c in s): return s.decode()
    return None

def pointer_fields(d):
    """lista de (posicion, ancho_bytes) de todos los punteros absolutos del archivo"""
    L = len(d); res = [(0, 4)]
    # punteros de actor
    for m in re.finditer(rb'\x21\x00\x00\x00RamaSave_PersistentActorUniqueID\x00', d):
        p = m.start()
        seg = d[max(0, p-400):p]; base = max(0, p-400)
        mm = list(re.finditer(rb'/Game/[ -~]+\.([ -~]+_C)\x00', seg))[-1]
        pathpos = base + mm.start() - 4
        res.append((pathpos - 4 - len(mm.group(1)) - 1 - 8, 8))
    # propiedades 'nombre + puntero'
    for m in re.finditer(rb'[\x02-\xc8]\x00\x00\x00[ -~]{1,199}\x00', d):
        p = m.start(); n = m.group()[0]
        if len(m.group()) != 4 + n: continue
        name = m.group()[4:-1]
        if name.endswith(b'Property') or name == b'None': continue
        q = p + 4 + n
        if q + 8 > L: continue
        x = struct.unpack_from('<q', d, q)[0]
        if x > q and x + 4 <= L and (x + 4 == L or _isfs(d, x + 4) is not None):
            res.append((q, 8))
    return res

def insert_ships(data, elements):
    """anade las naves (bytes) al final de PlayersShips y recalcula contadores, tamanos y punteros"""
    d = bytes(data); L = len(d)
    info = read_ships(d)
    P = info['end']; blob = b''.join(elements); delta = len(blob)
    fields = pointer_fields(d)
    new = bytearray(d[:P] + blob + d[P:])
    for pos, w in fields:
        v = struct.unpack_from('<q' if w == 8 else '<i', d, pos)[0]
        if v + 4 >= P and not (pos == info['ptr_pos'] and False):
            v += delta
        npos = pos if pos < P else pos + delta
        struct.pack_into('<q' if w == 8 else '<i', new, npos, v)
    struct.pack_into('<i', new, info['cnt_pos'], info['count'] + len(elements))
    sz = struct.unpack_from('<q', d, info['size_pos'])[0]
    struct.pack_into('<q', new, info['size_pos'], sz + delta)
    return bytes(new)


def list_ships(data):
    d = bytes(data)
    return [ship_info(d, s, e) for s, e in read_ships(d)['elems']]


def load_catalog():
    """plantillas de naves: lista de dicts (clase, nombre, nivel, tier, raw). Vacia si falta el archivo."""
    dirs = []
    if getattr(sys, '_MEIPASS', None):                 # ejecutable de PyInstaller: archivos empaquetados
        dirs.append(sys._MEIPASS)
    if getattr(sys, 'frozen', False):                  # ... o una copia junto al .exe
        dirs.append(os.path.dirname(sys.executable))
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    for d in dirs:
        try:
            with open(os.path.join(d, CATALOG_FILE), encoding='utf-8') as f:
                items = json.load(f)['ships']
            return [dict(clase=i['clase'], nombre=i.get('nombre', ''), nivel=i.get('nivel'), tier=i.get('tier'),
                         raw=zlib.decompress(base64.b64decode(i['bytes']))) for i in items]
        except Exception:
            continue
    return []


def new_ship(template, existing_codes, solar, station, tier=None, nivel=None):
    while True:
        code = str(random.randint(10 ** 9, 10 ** 10 - 1))
        if code not in existing_codes:
            existing_codes.add(code)
            return customize(template, code, solar, station, tier, nivel)


class SaveFile:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            self.raw = f.read()
        self.data = bytearray(decompress(self.raw))
        self.scan()

    def scan(self):
        view = bytes(self.data)
        self.offsets = {'dinero': money_offset(view)}
        for k, (_n, xp, lv, pts) in TIPOS.items():
            self.offsets[k + '_xp'] = int_prop_offset(view, xp)
            self.offsets[k + '_nivel'] = int_prop_offset(view, lv)
            self.offsets[k + '_puntos'] = int_prop_offset(view, pts)
        try:
            self.ships = list_ships(view)
        except Exception:
            self.ships = None   # este archivo no tiene lista de naves reconocible

    def add_ships(self, elements):
        self.data = bytearray(insert_ships(self.data, elements))
        self.scan()

    def get(self, key):
        return struct.unpack_from('<i', self.data, self.offsets[key])[0]

    def set(self, key, value):
        struct.pack_into('<i', self.data, self.offsets[key], int(value))

    def save(self, backup_dir):
        os.makedirs(backup_dir, exist_ok=True)
        stamp = time.strftime('%Y%m%d_%H%M%S')
        backup = os.path.join(backup_dir, f'{os.path.basename(self.path)}_{stamp}.bak')
        shutil.copy2(self.path, backup)
        new_raw = compress(bytes(self.data))
        if decompress(new_raw) != bytes(self.data):  # verificacion
            raise RuntimeError('Verification failed; nothing was written. / La verificación falló; no se escribió nada.')
        tmp = self.path + '.tmp_editor'
        with open(tmp, 'wb') as f:
            f.write(new_raw)
        os.replace(tmp, self.path)
        self.raw = new_raw
        return backup


def default_saves_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    return os.path.join(base, 'SB2', 'Saved', 'SaveGames')


def backups_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    return os.path.join(base, 'SB2', 'SaveEditor_Backups')




# ----------------------------------------------------------------------------
# Idiomas / Languages
# ----------------------------------------------------------------------------
LANGS = ('es', 'en')

STR = {
    'es': {
        'title': 'SpaceBourne 2 - Editor de guardados',
        'saves_folder': 'Carpeta de guardados:', 'browse': 'Examinar...', 'refresh': 'Actualizar',
        'saves_found': 'Guardados encontrados',
        'col_file': 'Archivo', 'col_size': 'Tamaño', 'col_modified': 'Modificado',
        'tab_char': 'Personaje', 'tab_ships': 'Naves',
        'save_btn': 'Guardar cambios', 'discard': 'Descartar',
        'status_initial': 'Cierra el juego antes de guardar cambios.',
        'money': 'Dinero (TY)',
        'area_piloto': 'Piloto', 'area_soldado': 'Soldado', 'area_explorador': 'Explorador',
        'level_colon': 'Nivel:', 'apply_level': 'Aplicar nivel',
        'points_note': 'Al subir de nivel se suman {n} puntos de atributo por cada nivel ganado.\nBajar el nivel no quita puntos.',
        'lbl_level': 'Nivel', 'lbl_xp': 'XP', 'lbl_points': 'Puntos',
        'ships_open': 'Abre un guardado para ver sus naves.',
        'ships_unrecognized': 'Este archivo no tiene una lista de naves reconocible.',
        'ships_count': 'Naves en el guardado: {n}',
        'ship_col_ship': 'Nave', 'ship_col_name': 'Nombre', 'ship_col_lvl': 'Niv', 'ship_col_tier': 'Tier',
        'ship_col_loc': 'Ubicación',
        'catalog_missing': 'No se encontró {file} junto al editor.\nSin ese archivo no se pueden añadir naves.',
        'ship_colon': 'Nave:', 'tier_colon': 'Tier:', 'hint_max': '(máximo {n})',
        'add_ship': 'Añadir nave', 'add_missing': 'Añadir todas las que faltan', 'clear_pending': 'Vaciar pendientes',
        'ships_note': 'Todas las naves nuevas aparecen en {station} ({solar}). El tier va de {tmin} a {tmax} y el nivel '
                      'no puede superar tu nivel de piloto. Salen con código único, marcadas como tuyas y sin piloto.',
        'in_space': '(en el espacio)',
        'pending_ships': 'Por añadir ({n}): {txt}', 'pending_item': '{name} (tier {t}, nivel {l})',
        'err_tier_level_int': 'Tier y nivel deben ser números enteros.',
        'err_tier_range': 'El tier debe estar entre {tmin} y {tmax}.',
        'err_level_range': 'El nivel debe estar entre 1 y tu nivel de piloto ({top}).',
        'pick_ship': 'Elige una nave del catálogo.',
        'err_level_int': 'Escribe un número entero para el nivel.',
        'folder_missing': 'No existe la carpeta. Usa "Examinar..." para elegirla.',
        'files_found': '{n} archivo(s) en la carpeta. Elige uno.', 'folder_empty': 'La carpeta no tiene archivos.',
        'reading': 'Leyendo...', 'read_fail': 'Ese archivo no se pudo leer como guardado del juego.',
        'read_fail_title': 'No se pudo leer', 'loaded': 'Cargado: {name}',
        'unsaved': 'Cambios sin guardar.', 'discarded': 'Cambios descartados.',
        'confirm_unsaved_title': 'Cambios sin guardar',
        'confirm_unsaved': 'Hay cambios sin guardar. ¿Los descartas?',
        'save_title': 'Guardar',
        'save_confirm': 'El juego debe estar cerrado.\nSe hará una copia de seguridad antes de escribir.\n\n¿Guardar los cambios?',
        'error_title': 'Error', 'save_error': 'No se guardó:\n{err}', 'saved': 'Guardado. Copia en: {path}',
        'no_tk': 'Esta instalación de Python no tiene tkinter.',
    },
    'en': {
        'title': 'SpaceBourne 2 - Save Editor',
        'saves_folder': 'Saves folder:', 'browse': 'Browse...', 'refresh': 'Refresh',
        'saves_found': 'Saves found',
        'col_file': 'File', 'col_size': 'Size', 'col_modified': 'Modified',
        'tab_char': 'Character', 'tab_ships': 'Ships',
        'save_btn': 'Save changes', 'discard': 'Discard',
        'status_initial': 'Close the game before saving changes.',
        'money': 'Money (TY)',
        'area_piloto': 'Pilot', 'area_soldado': 'Soldier', 'area_explorador': 'Explorer',
        'level_colon': 'Level:', 'apply_level': 'Apply level',
        'points_note': 'Raising the level adds {n} attribute points for each level gained.\nLowering the level does not remove points.',
        'lbl_level': 'Level', 'lbl_xp': 'XP', 'lbl_points': 'Points',
        'ships_open': 'Open a save to see its ships.',
        'ships_unrecognized': 'This file has no recognizable ship list.',
        'ships_count': 'Ships in the save: {n}',
        'ship_col_ship': 'Ship', 'ship_col_name': 'Name', 'ship_col_lvl': 'Lvl', 'ship_col_tier': 'Tier',
        'ship_col_loc': 'Location',
        'catalog_missing': 'Could not find {file} next to the editor.\nShips cannot be added without that file.',
        'ship_colon': 'Ship:', 'tier_colon': 'Tier:', 'hint_max': '(max {n})',
        'add_ship': 'Add ship', 'add_missing': 'Add all missing', 'clear_pending': 'Clear pending',
        'ships_note': 'All new ships appear at {station} ({solar}). Tier ranges from {tmin} to {tmax} and the level '
                      'cannot exceed your pilot level. They get a unique code, are marked as yours and have no pilot.',
        'in_space': '(in space)',
        'pending_ships': 'To add ({n}): {txt}', 'pending_item': '{name} (tier {t}, level {l})',
        'err_tier_level_int': 'Tier and level must be whole numbers.',
        'err_tier_range': 'Tier must be between {tmin} and {tmax}.',
        'err_level_range': 'Level must be between 1 and your pilot level ({top}).',
        'pick_ship': 'Choose a ship from the catalog.',
        'err_level_int': 'Enter a whole number for the level.',
        'folder_missing': 'The folder does not exist. Use "Browse..." to choose it.',
        'files_found': '{n} file(s) in the folder. Choose one.', 'folder_empty': 'The folder has no files.',
        'reading': 'Reading...', 'read_fail': 'That file could not be read as a game save.',
        'read_fail_title': 'Could not read', 'loaded': 'Loaded: {name}',
        'unsaved': 'Unsaved changes.', 'discarded': 'Changes discarded.',
        'confirm_unsaved_title': 'Unsaved changes',
        'confirm_unsaved': 'There are unsaved changes. Discard them?',
        'save_title': 'Save',
        'save_confirm': 'The game must be closed.\nA backup will be made before writing.\n\nSave the changes?',
        'error_title': 'Error', 'save_error': 'Not saved:\n{err}', 'saved': 'Saved. Backup at: {path}',
        'no_tk': 'This Python install does not have tkinter.',
    },
}


def settings_path():
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    return os.path.join(base, 'SB2', 'SaveEditor_settings.json')


def load_lang():
    """idioma guardado la ultima vez (None si no hay)"""
    try:
        with open(settings_path(), encoding='utf-8') as f:
            lang = json.load(f).get('lang')
        return lang if lang in LANGS else None
    except Exception:
        return None


def store_lang(lang):
    try:
        os.makedirs(os.path.dirname(settings_path()), exist_ok=True)
        with open(settings_path(), 'w', encoding='utf-8') as f:
            json.dump({'lang': lang}, f)
    except Exception:
        pass


def fmt(n, lang='es'):
    s = f'{n:,}'
    return s.replace(',', '.') if lang == 'es' else s


def fmt_size(nbytes, lang='es'):
    return f'{fmt(round(nbytes / 1024), lang)} KB'


def fmt_time(ts, lang='es'):
    return time.strftime('%d/%m/%Y %H:%M' if lang == 'es' else '%Y-%m-%d %H:%M', time.localtime(ts))


# ----------------------------------------------------------------------------
# Interfaz
# ----------------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.lang = load_lang() or 'es'
        self._i18n = []          # funciones que reaplican los textos fijos al cambiar de idioma
        self._status = ('status_initial', {})
        root.geometry('1100x600')
        root.minsize(1000, 560)
        self.save = None
        self.pending = {}
        self.cur_item = None
        self.value_labels = {}
        self.level_vars = {}
        self.buttons = []
        self.pending_ships = []
        self.catalog = load_catalog()
        self.ship_widgets = []

        top = ttk.Frame(root, padding=8)
        top.pack(fill='x')
        self.btn_lang = ttk.Button(top, width=10, command=self.toggle_language)
        self.btn_lang.pack(side='right', padx=(12, 0))
        self.L(ttk.Label(top), 'saves_folder').pack(side='left')
        self.dir_var = tk.StringVar(value=default_saves_dir())
        ttk.Entry(top, textvariable=self.dir_var).pack(side='left', fill='x', expand=True, padx=6)
        self.L(ttk.Button(top, command=self.browse), 'browse').pack(side='left')
        self.L(ttk.Button(top, command=self.refresh), 'refresh').pack(side='left', padx=(6, 0))

        body = ttk.Frame(root, padding=(8, 0))
        body.pack(fill='both', expand=True)

        left = self.L(ttk.LabelFrame(body, padding=6), 'saves_found')
        left.pack(side='left', fill='both', expand=True)
        cols = ('nombre', 'tam', 'fecha')
        self.tree = ttk.Treeview(left, columns=cols, show='headings', selectmode='browse', height=10)
        for c, key, w in (('nombre', 'col_file', 150), ('tam', 'col_size', 70), ('fecha', 'col_modified', 110)):
            self.H(self.tree, c, key)
            self.tree.column(c, width=w, anchor='w')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.on_select)

        right = ttk.Notebook(body)
        right.pack(side='left', fill='y', padx=(8, 0))
        tab1 = ttk.Frame(right, padding=10)
        right.add(tab1)
        self.T(right, tab1, 'tab_char')
        self.build_right(tab1)
        tab2 = ttk.Frame(right, padding=10)
        right.add(tab2)
        self.T(right, tab2, 'tab_ships')
        self.build_ships(tab2)

        bottom = ttk.Frame(root, padding=8)
        bottom.pack(fill='x')
        self.btn_save = self.L(ttk.Button(bottom, command=self.save_changes, state='disabled'), 'save_btn')
        self.btn_save.pack(side='left')
        self.btn_discard = self.L(ttk.Button(bottom, command=self.discard, state='disabled'), 'discard')
        self.btn_discard.pack(side='left', padx=6)
        self.status = tk.StringVar(value='')
        ttk.Label(bottom, textvariable=self.status).pack(side='left', padx=12)

        self.apply_language()
        self.refresh()

    # --- idiomas
    def tr(self, key, **kw):
        txt = STR[self.lang][key]
        return txt.format(**kw) if kw else txt

    def L(self, widget, key, option='text', **kw):
        """registra un texto fijo traducible y lo aplica"""
        def apply():
            widget.config(**{option: self.tr(key, **kw)})
        self._i18n.append(apply)
        return widget

    def H(self, tree, col, key):
        self._i18n.append(lambda: tree.heading(col, text=self.tr(key)))

    def T(self, nb, tab, key):
        self._i18n.append(lambda: nb.tab(tab, text=self.tr(key)))

    def toggle_language(self):
        self.lang = 'en' if self.lang == 'es' else 'es'
        store_lang(self.lang)
        self.apply_language()

    def apply_language(self):
        self.root.title(self.tr('title'))
        for apply in self._i18n:
            apply()
        self.btn_lang.config(text='English' if self.lang == 'es' else 'Español')
        self.render()

    def render(self):
        """vuelve a dibujar todo lo que depende del idioma sin tocar el estado (guardado abierto, cambios)"""
        for f in self.tree.get_children():
            self.tree.item(f, values=self.file_row(f))
        sel = self.selected_class()
        self.catalog.sort(key=lambda c: nombre_nave(c['clase'], self.lang))
        self.refresh_ships_tab(keep_class=sel)
        if self.save:
            self.update_view(notify=False)
        self.show_status()

    def set_status(self, key, **kw):
        self._status = (key, kw)
        self.show_status()

    def show_status(self):
        key, kw = self._status
        self.status.set(self.tr(key, **kw))

    # --- panel del personaje
    def build_right(self, parent):
        r = 0
        self.L(ttk.Label(parent, font=('Segoe UI', 10, 'bold')), 'money').grid(row=r, column=0, sticky='w')
        lbl = ttk.Label(parent, text='-', width=48)
        lbl.grid(row=r, column=1, columnspan=2, sticky='w', padx=8)
        self.value_labels['dinero'] = lbl
        r += 1
        self.add_btn(parent, r, 1, '+500k', 'dinero', 500_000)
        self.add_btn(parent, r, 2, '+3M', 'dinero', 3_000_000)
        r += 1
        ttk.Separator(parent).grid(row=r, column=0, columnspan=3, sticky='ew', pady=8)
        for k in TIPOS:
            r += 1
            self.L(ttk.Label(parent, font=('Segoe UI', 10, 'bold')), 'area_' + k).grid(row=r, column=0, sticky='w')
            lbl = ttk.Label(parent, text='-', width=48)
            lbl.grid(row=r, column=1, columnspan=2, sticky='w', padx=8)
            self.value_labels[k] = lbl
            r += 1
            self.add_btn(parent, r, 1, '+100k XP', k + '_xp', 100_000)
            self.add_btn(parent, r, 2, '+1M XP', k + '_xp', 1_000_000)
            r += 1
            self.L(ttk.Label(parent), 'level_colon').grid(row=r, column=0, sticky='e')
            var = tk.StringVar(value='')
            self.level_vars[k] = var
            sp = ttk.Spinbox(parent, from_=1, to=MAX_NIVEL, textvariable=var, width=10, state='disabled')
            sp.grid(row=r, column=1, padx=4, pady=1)
            self.buttons.append(sp)
            b = self.L(ttk.Button(parent, width=14, state='disabled', command=lambda kk=k: self.apply_level(kk)),
                       'apply_level')
            b.grid(row=r, column=2, padx=4, pady=1)
            self.buttons.append(b)
            r += 1
            ttk.Separator(parent).grid(row=r, column=0, columnspan=3, sticky='ew', pady=8)
        r += 1
        self.L(ttk.Label(parent, justify='left', foreground='#555555'), 'points_note',
               n=PUNTOS_POR_NIVEL).grid(row=r, column=0, columnspan=3, sticky='w')

    def add_btn(self, parent, row, col, text, key, amount):
        b = ttk.Button(parent, text=text, width=14, state='disabled',
                       command=lambda: self.add(key, amount))
        b.grid(row=row, column=col, padx=4, pady=1)
        self.buttons.append(b)

    # --- naves
    def build_ships(self, parent):
        self.ships_info = tk.StringVar(value='')
        ttk.Label(parent, textvariable=self.ships_info, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        cols = ('clase', 'nombre', 'nivel', 'tier', 'ubic')
        self.ship_tree = ttk.Treeview(parent, columns=cols, show='headings', height=9, selectmode='none')
        for c, key, w in (('clase', 'ship_col_ship', 170), ('nombre', 'ship_col_name', 110), ('nivel', 'ship_col_lvl', 40),
                          ('tier', 'ship_col_tier', 40), ('ubic', 'ship_col_loc', 170)):
            self.H(self.ship_tree, c, key)
            self.ship_tree.column(c, width=w, anchor='w')
        self.ship_tree.pack(fill='x', pady=6)
        if not self.catalog:
            self.L(ttk.Label(parent, foreground='#a00000', justify='left'), 'catalog_missing',
                   file=CATALOG_FILE).pack(anchor='w')
            return
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=2)
        self.L(ttk.Label(row, width=8), 'ship_colon').pack(side='left')
        self.ship_var = tk.StringVar()
        self.ship_cb = ttk.Combobox(row, textvariable=self.ship_var, state='disabled', width=38)
        self.ship_cb.pack(side='left', padx=4)
        self.ship_cb.bind('<<ComboboxSelected>>', self.on_ship_selected)
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=2)
        self.L(ttk.Label(row, width=8), 'tier_colon').pack(side='left')
        self.tier_var = tk.StringVar(value='1')
        sp = ttk.Spinbox(row, from_=TIER_MIN, to=TIER_MAX, textvariable=self.tier_var, width=6, state='disabled')
        sp.pack(side='left', padx=4)
        self.ship_widgets.append(sp)
        self.L(ttk.Label(row), 'level_colon').pack(side='left', padx=(12, 0))
        self.nivel_var = tk.StringVar(value='1')
        self.nivel_sp = ttk.Spinbox(row, from_=1, to=MAX_NIVEL, textvariable=self.nivel_var, width=6, state='disabled')
        self.nivel_sp.pack(side='left', padx=4)
        self.ship_widgets.append(self.nivel_sp)
        self.nivel_hint = tk.StringVar(value='')
        ttk.Label(row, textvariable=self.nivel_hint, foreground='#555555').pack(side='left', padx=6)
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=6)
        b = self.L(ttk.Button(row, state='disabled', command=self.add_ship_clicked), 'add_ship')
        b.pack(side='left')
        self.ship_widgets.append(b)
        b = self.L(ttk.Button(row, state='disabled', command=self.add_missing_ships), 'add_missing')
        b.pack(side='left', padx=6)
        self.ship_widgets.append(b)
        b = self.L(ttk.Button(row, state='disabled', command=self.clear_pending_ships), 'clear_pending')
        b.pack(side='left')
        self.ship_widgets.append(b)
        self.pending_ships_var = tk.StringVar(value='')
        ttk.Label(parent, textvariable=self.pending_ships_var, wraplength=520, justify='left').pack(anchor='w')
        self.L(ttk.Label(parent, justify='left', foreground='#555555', wraplength=520), 'ships_note',
               station=GUILD_STATION, solar=GUILD_SOLAR, tmin=TIER_MIN, tmax=TIER_MAX).pack(anchor='w', pady=(6, 0))

    def ship_name(self, clase):
        return nombre_nave(clase, self.lang)

    def selected_class(self):
        if not (self.catalog and hasattr(self, 'ship_cb')):
            return None
        i = self.ship_cb.current()
        return self.catalog[i]['clase'] if 0 <= i < len(self.catalog) else None

    def dock_text(self, sh):
        solar, station = sh.get('DockedSolarID', ''), sh.get('DockedStationName', '')
        if solar in ('', 'None') and not station:
            return self.tr('in_space')
        return f'{station or "?"} ({solar})'

    def pilot_level(self):
        """nivel de piloto del jugador (incluye un cambio pendiente)"""
        return self.value('piloto_nivel') if self.save else 1

    def default_ship_values(self, c):
        tier = min(max(int(c['tier'] or TIER_MIN), TIER_MIN), TIER_MAX)
        nivel = max(1, min(int(c['nivel'] or 1), self.pilot_level()))
        return tier, nivel

    def on_ship_selected(self, _e=None):
        i = self.ship_cb.current()
        if i >= 0 and self.save:
            tier, nivel = self.default_ship_values(self.catalog[i])
            self.tier_var.set(str(tier))
            self.nivel_var.set(str(nivel))

    def refresh_ships_tab(self, keep_class=None):
        self.ship_tree.delete(*self.ship_tree.get_children())
        ships = self.save.ships if self.save else None
        if ships is None:
            self.ships_info.set(self.tr('ships_unrecognized') if self.save else self.tr('ships_open'))
        else:
            for i, sh in enumerate(ships):
                self.ship_tree.insert('', 'end', iid=str(i), values=(
                    self.ship_name(sh.get('clase', '?')), sh.get('ShipName', ''), sh.get('ShipLevel', ''),
                    sh.get('ShipTier', ''), self.dock_text(sh)))
            self.ships_info.set(self.tr('ships_count', n=len(ships)))
        if not self.catalog:
            return
        self.ship_cb.config(values=[self.ship_name(c['clase']) for c in self.catalog])
        if keep_class:
            idx = next((i for i, c in enumerate(self.catalog) if c['clase'] == keep_class), -1)
            if idx >= 0:
                self.ship_cb.current(idx)
        usable = ships is not None
        self.ship_cb.config(state='readonly' if usable else 'disabled')
        for w in self.ship_widgets:
            w.config(state='normal' if usable else 'disabled')
        self.update_pending_ships_label()

    def read_tier_level(self):
        """tier y nivel escritos en la pantalla, validados; None si no son validos"""
        try:
            tier, nivel = int(self.tier_var.get()), int(self.nivel_var.get())
        except ValueError:
            self.set_status('err_tier_level_int')
            return None
        top = self.pilot_level()
        if not TIER_MIN <= tier <= TIER_MAX:
            self.set_status('err_tier_range', tmin=TIER_MIN, tmax=TIER_MAX)
            return None
        if not 1 <= nivel <= top:
            self.set_status('err_level_range', top=top)
            return None
        return tier, nivel

    def add_ship_clicked(self):
        i = self.ship_cb.current()
        if i < 0:
            self.set_status('pick_ship')
            return
        tl = self.read_tier_level()
        if tl:
            self.add_ship(self.catalog[i]['clase'], *tl)

    def add_ship(self, clase, tier, nivel):
        if not (self.save and self.save.ships is not None):
            return
        self.pending_ships.append((clase, tier, nivel))
        self.update_view()

    def add_missing_ships(self):
        """anade las clases que faltan, cada una con el tier de su plantilla y un nivel que respeta el tope"""
        if not (self.save and self.save.ships is not None):
            return
        have = {sh.get('clase') for sh in self.save.ships} | {p[0] for p in self.pending_ships}
        for c in self.catalog:
            if c['clase'] not in have:
                self.pending_ships.append((c['clase'], *self.default_ship_values(c)))
        self.update_view()

    def clear_pending_ships(self):
        self.pending_ships = []
        self.update_view()

    def update_pending_ships_label(self):
        if not self.catalog:
            return
        self.nivel_hint.set(self.tr('hint_max', n=self.pilot_level()) if self.save else '')
        if not self.pending_ships:
            self.pending_ships_var.set('')
            return
        counts = {}
        for p in self.pending_ships:
            counts[p] = counts.get(p, 0) + 1
        txt = ', '.join(self.tr('pending_item', name=self.ship_name(c), t=t, l=n) + (f' x{k}' if k > 1 else '')
                        for (c, t, n), k in counts.items())
        self.pending_ships_var.set(self.tr('pending_ships', n=len(self.pending_ships), txt=txt))

    # --- lista de guardados
    def file_row(self, f):
        try:
            st = os.stat(os.path.join(self.dir_var.get(), f))
            return (f, fmt_size(st.st_size, self.lang), fmt_time(st.st_mtime, self.lang))
        except OSError:
            return (f, '?', '?')

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get() if os.path.isdir(self.dir_var.get()) else None)
        if d:
            self.dir_var.set(d)
            self.refresh()

    def refresh(self):
        if not self.confirm_discard():
            return
        self.tree.delete(*self.tree.get_children())
        self.clear_save()
        d = self.dir_var.get()
        if not os.path.isdir(d):
            self.set_status('folder_missing')
            return
        files = [f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)) and not f.endswith('.tmp_editor')]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
        for f in files:
            self.tree.insert('', 'end', iid=f, values=self.file_row(f))
        if files:
            self.set_status('files_found', n=len(files))
        else:
            self.set_status('folder_empty')

    def on_select(self, _e=None):
        sel = self.tree.selection()
        if not sel or sel[0] == self.cur_item:
            return
        if not self.confirm_discard():
            if self.cur_item and self.tree.exists(self.cur_item):
                self.tree.selection_set(self.cur_item)
            return
        path = os.path.join(self.dir_var.get(), sel[0])
        self.set_status('reading')
        self.root.update_idletasks()
        try:
            self.save = SaveFile(path)
        except Exception as e:
            self.clear_save()
            self.cur_item = sel[0]
            self.set_status('read_fail')
            messagebox.showwarning(self.tr('read_fail_title'), f'{sel[0]}\n\n{e}')
            return
        self.cur_item = sel[0]
        self.pending = {}
        self.pending_ships = []
        self.sync_level_vars()
        self.refresh_ships_tab()
        self.update_view(notify=False)
        for b in self.buttons:
            b.config(state='normal')
        self.set_status('loaded', name=sel[0])

    def clear_save(self):
        self.save = None
        self.pending = {}
        self.pending_ships = []
        self.cur_item = None
        self.refresh_ships_tab()
        for w in self.ship_widgets:
            w.config(state='disabled')
        for lbl in self.value_labels.values():
            lbl.config(text='-')
        for v in self.level_vars.values():
            v.set('')
        for b in self.buttons + [self.btn_save, self.btn_discard]:
            b.config(state='disabled')

    # --- edicion
    def value(self, key):
        return self.pending.get(key, self.save.get(key))

    def add(self, key, amount):
        if not self.save:
            return
        new = min(self.value(key) + amount, INT_MAX)
        self.pending[key] = new
        self.update_view()

    def set_level(self, k, n):
        """Fija el nivel del area k. Si sube, suma PUNTOS_POR_NIVEL por cada nivel ganado
        (siempre respecto al nivel y los puntos del archivo, asi no se acumulan de mas)."""
        s = self.save
        n = max(1, min(MAX_NIVEL, int(n)))
        lv0, pt0 = s.get(k + '_nivel'), s.get(k + '_puntos')
        if n == lv0:
            self.pending.pop(k + '_nivel', None)
            self.pending.pop(k + '_puntos', None)
        else:
            self.pending[k + '_nivel'] = n
            if n > lv0:
                self.pending[k + '_puntos'] = min(pt0 + PUNTOS_POR_NIVEL * (n - lv0), INT_MAX)
            else:
                self.pending.pop(k + '_puntos', None)
        return n

    def apply_level(self, k):
        if not self.save:
            return
        try:
            n = self.set_level(k, int(self.level_vars[k].get()))
        except ValueError:
            self.set_status('err_level_int')
            return
        self.level_vars[k].set(str(n))
        self.update_view()

    def sync_level_vars(self):
        for k in TIPOS:
            self.level_vars[k].set(str(self.value(k + '_nivel')))

    def update_view(self, notify=True):
        s, lang = self.save, self.lang

        def show(label, key):
            txt = f'{label} {fmt(s.get(key), lang)}'
            if key in self.pending:
                txt += f' -> {fmt(self.pending[key], lang)}'
            return txt

        txt = fmt(s.get('dinero'), lang)
        if 'dinero' in self.pending:
            txt += f' -> {fmt(self.pending["dinero"], lang)}'
        self.value_labels['dinero'].config(text=txt)
        for k in TIPOS:
            self.value_labels[k].config(text='   |   '.join((
                show(self.tr('lbl_level'), k + '_nivel'), show(self.tr('lbl_xp'), k + '_xp'),
                show(self.tr('lbl_points'), k + '_puntos'))))
        self.update_pending_ships_label()
        has = bool(self.pending) or bool(self.pending_ships)
        self.btn_save.config(state='normal' if has else 'disabled')
        self.btn_discard.config(state='normal' if has else 'disabled')
        if has and notify:
            self.set_status('unsaved')

    def discard(self):
        self.pending = {}
        self.pending_ships = []
        if self.save:
            self.sync_level_vars()
            self.update_view(notify=False)
            self.set_status('discarded')

    def confirm_discard(self):
        if self.pending or self.pending_ships:
            return messagebox.askyesno(self.tr('confirm_unsaved_title'), self.tr('confirm_unsaved'))
        return True

    def save_changes(self):
        if not (self.save and (self.pending or self.pending_ships)):
            return
        if not messagebox.askyesno(self.tr('save_title'), self.tr('save_confirm')):
            return
        try:
            for k, v in self.pending.items():
                self.save.set(k, v)
            if self.pending_ships:
                top = self.save.get('piloto_nivel')   # el nivel de piloto ya incluye el cambio pendiente
                existing = {sh.get('ShipBarkot') for sh in (self.save.ships or [])}
                tpl = {c['clase']: c['raw'] for c in self.catalog}
                self.save.add_ships([
                    new_ship(tpl[c], existing, GUILD_SOLAR, GUILD_STATION,
                             min(max(t, TIER_MIN), TIER_MAX), max(1, min(n, top)))
                    for c, t, n in self.pending_ships])
            backup = self.save.save(backups_dir())
        except Exception as e:
            messagebox.showerror(self.tr('error_title'), self.tr('save_error', err=e))
            return
        self.pending = {}
        self.pending_ships = []
        self.sync_level_vars()
        self.refresh_ships_tab()
        self.update_view(notify=False)
        self.set_status('saved', path=backup)
        self.refresh_row()

    def refresh_row(self):
        if self.cur_item and self.tree.exists(self.cur_item):
            self.tree.item(self.cur_item, values=self.file_row(self.cur_item))


def main():
    if tk is None:
        raise SystemExit(STR[load_lang() or 'es']['no_tk'])
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
