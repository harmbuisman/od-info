from enum import Enum

from opsdata.schema import *
from domain.military import military_for
from domain.castle import castle_for
from domain.land import land_for
from domain.buildings import buildings_for
from domain.magic import revelation_for
from domain.refdata import Race
from domain.technology import tech_for
from domain.refdata import NETWORTH_VALUES
from domain.unknown import Unknown

QRY_SELECT_ALL_DOMS = '''
    SELECT 
        d.code, d.name, d.realm, d.role, dh.land, dh.networth, d.player, d.race, d.last_op, max(dh.timestamp) 
    FROM 
        Dominions d
    LEFT JOIN 
        DominionHistory dh on d.code = dh.dominion
    GROUP BY d.code
    ORDER BY dh.land
'''


def all_doms(db) -> list:
    return db.query(QRY_SELECT_ALL_DOMS)


def name_for_code(db, dom_code) -> str:
    return db.query('SELECT name FROM Dominions WHERE code = :dom_code', {'dom_code': dom_code}, one=True)['name']


def realm_of_dom(db, dom_code):
    return db.query('SELECT realm FROM Dominions WHERE code = :dom_code', {'dom_code': dom_code}, one=True)['realm']


def dom_codes_of_realm(db, realm) -> list[int]:
    result = db.query('SELECT code FROM Dominions WHERE realm = :realm', {'realm': realm})
    return [dom['code'] for dom in result]


def doms_of_realm(db, realm) -> list:
    return [Dominion(db, code) for code in dom_codes_of_realm(db, realm)]


class WarStatus(Enum):
    NONE = 0
    WAR = 1
    MUTUAL = 2


class Dominion(object):
    def __init__(self, db, domcode: int):
        self.code: int = domcode
        self.db = db
        self.data = query_dominion(self.db, self.code)
        self.history = query_dom_history(self.db, self.code, latest=True)
        self._cs = None
        self._military = None
        self._buildings = None
        self._castle = None
        self._land = None
        self._race = None
        self._technology = None
        self._magic = None
        self.war_status = WarStatus.NONE

    @property
    def military(self):
        if not self._military:
            self._military = military_for(self.db, self)
        return self._military

    @property
    def buildings(self):
        if not self._buildings:
            self._buildings = buildings_for(self.db, self)
        return self._buildings

    @property
    def castle(self):
        if not self._castle:
            self._castle = castle_for(self.db, self)
        return self._castle

    @property
    def magic(self):
        if not self._magic:
            self._magic = revelation_for(self.db, self)
        return self._magic

    @property
    def cs(self):
        if not self._cs:
            result = query_clearsight(self.db, self.code, latest=True)
            self._cs = result if result is not None else Unknown()
        return self._cs

    @property
    def land(self):
        if not self._land:
            self._land = land_for(self.db, self)
        return self._land

    @property
    def total_land(self):
        return self.history['land']

    @property
    def name(self) -> str:
        return self.data['name']

    @property
    def realm(self):
        return self.data['realm']

    @property
    def player(self) -> str:
        return self.data['player']

    @property
    def calc_networth(self) -> int:
        networth = 0
        networth += self.land * NETWORTH_VALUES['land']
        networth += self.buildings.total * NETWORTH_VALUES['buildings']

        networth += self.military.amount(1) * NETWORTH_VALUES['specs']
        networth += self.military.amount(2) * NETWORTH_VALUES['specs']
        networth += self.military.amount(3) * self.race.def_elite.networth
        networth += self.military.amount(4) * self.race.off_elite.networth

        networth += self.military.spies * NETWORTH_VALUES['spywiz']
        networth += self.military.assassings * NETWORTH_VALUES['spywiz']
        networth += self.military.wizards * NETWORTH_VALUES['spywiz']
        networth += self.military.archmages * NETWORTH_VALUES['spywiz']
        return round(networth)

    @property
    def networth(self) -> int:
        return self.cs['networth']

    @property
    def race(self) -> Race:
        if not self._race:
            self._race = Race(self.data['race'], self)
        return self._race

    @property
    def population_bonus(self) -> float:
        # return (1 + self.castle.keep +
        #         self.tech.pop_bonus +
        #         self.wonder_bonus) * (1 + self.prestige_bonus)
        return (1 + self.castle.keep +
                self.tech.pop_bonus) * (1 + self.prestige_bonus)

    @property
    def prestige_bonus(self) -> float:
        return 1 + (self.cs['prestige'] / 10000)

    @property
    def tech(self):
        if not self._technology:
            self._technology = tech_for(self.db, self)
        return self._technology

    @property
    def last_op(self):
        return self.data['last_op']

    @property
    def last_op_since(self) -> int:
        return hours_since(self.last_op)


if __name__ == '__main__':
    from opsdata.db import Database
    from config import DATABASE
    db = Database()
    print("Opening database", DATABASE)
    db.init(DATABASE)
    # dom = Dominion(db, 10756)
    dom = Dominion(db, 10794)
    # dom = Dominion(db, 10793)
    print("Name:", dom.name)
    print("Code:", dom.code)
    print("Pop Bonus:", dom.population_bonus)
    print("Military:", dom.military)
    print("Nightshade:", dom.military.unit_type(3).defense)
    print("Swamp %:", dom.land.ratio_of('swamp'))
    print("Castle:", dom.castle)
    print("Buildings:", dom.buildings)
    print("Mason bonus:", dom.castle.mason_bonus)
    print("Spies:", dom.military.spies)
    print("Spywiz NW:", dom.military.spywiz_networth)
    print("Spywiz estimate:", dom.military.ratio_estimate)
    print("Land:", dom.land)
    print("Race:", dom.race)
    print("CS:", row_s_to_dict(dom.cs))
    print("OP:", dom.military.op)
    print("DP:", dom.military.dp)
    print("5/4:", dom.military.five_over_four_op)
    print("Last op", dom.last_op)
    print("Last op since:", dom.last_op_since)
    print("Ares:", dom.magic.ares)
    for spell in dom.magic.spells:
        print(row_s_to_dict(spell))

