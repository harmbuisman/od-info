"""
Facade object to ensure that all "business and data logic" doesn't get mixed into user interface code.

This class is intentianally the smorgasbord of queries and actions that the UI (flask_app) needs
so that any ugliness is contained in this class.
"""

from operator import itemgetter

from calculators.economy import Economy
from calculators.networthcalculator import get_networth_deltas
from config import DATABASE, DB_SCHEMA_FILE, SEARCH_PAGE
from domain.dominion import all_doms, name_for_code, Dominion, dom_codes_of_realm, realm_of_dom, doms_of_realm
from facade.discord import send_to_webhook
from opsdata.db import Database
from opsdata.ops import grab_ops, grab_my_ops, update_dom_index, get_last_scans
from opsdata.schema import *
from opsdata.scrapetools import login, read_tick_time, get_soup_page
from opsdata.updater import update_ops, update_town_crier
from config import current_player_id
from domain.unknown import Unknown

logger = logging.getLogger('od-info.facade')


class ODInfoFacade(object):
    def __init__(self):
        self._session = None
        self._db = Database()
        if self._db.init(DATABASE, DB_SCHEMA_FILE):
            update_dom_index(self.session, self._db)

    @property
    def session(self):
        if not self._session:
            self._session = login(current_player_id)
        return self._session

    def teardown(self):
        self.session.close()
        self._db.teardown()
        self._db = None

    def update_all(self):
        last_scans = get_last_scans(self.session)
        for dom in all_doms(self._db):
            domcode = dom['code']
            if (domcode in last_scans) and (
                    (dom['last_op'] is None) or
                    (dom['last_op'] < last_scans[domcode])):
                self.update_ops(domcode)

    # ---------------------------------------- COMMANDS - Update from OpenDominion.net

    def update_dom_index(self):
        update_dom_index(self.session, self._db)

    def update_ops(self, dom_code):
        logger.debug("Updating ops for dominion %s", dom_code)
        if int(dom_code) == int(current_player_id):
            ops = grab_my_ops(self.session)
        else:
            ops = grab_ops(self.session, dom_code)
        if ops:
            update_ops(ops, self._db, dom_code)
        else:
            logger.warn(f"Can't get ops for dominion {dom_code}")

    def update_town_crier(self):
        update_town_crier(self.session, self._db)

    def update_realmies(self):
        for dom_code in self.realmie_codes():
            self.update_ops(dom_code)

    # ---------------------------------------- COMMANDS - Change directly

    def update_role(self, dom_code, role):
        logger.debug("Updating dominion %s role to %s", dom_code, role)
        qry = f'UPDATE Dominions SET role = ? WHERE code = ?'
        self._db.execute(qry, (role, dom_code))

    def update_player(self, dom_code, player_name):
        logger.debug("Updating dominion player name from %s to %s", dom_code, player_name)
        qry = f'UPDATE Dominions SET player = ? WHERE code = ?'
        self._db.execute(qry, (player_name, dom_code))

    # ---------------------------------------- COMMANDS - Send out information

    def send_top_bot_nw_to_discord(self):
        def create_message(header, nw_list):
            msg_content = '\n'.join([f"{item['name']:<50} {item['realm']:>5} {item['nwdelta']:>9} {item['networth']:>9} {item['land']:>5}" for item in nw_list])
            return f"{header}\n```{'Dominion':<50} {'Realm':>5} {'Delta':>9} {'Networth':>9} {'Land':>5}\n\n{msg_content}```"

        header_top = '**Top 10 Networth Growers since past 12 hours**'
        top10_message = create_message(header_top, self.get_top_bot_nw(filter_zeroes=True))
        header_bot = '**Top 10 Networth *Sinkers* since past 12 hours**'
        bot10_message = create_message(header_bot, self.get_top_bot_nw(top=False, filter_zeroes=True))
        nr_networth_unchanged = 10
        header_unchanged = f'**Top {nr_networth_unchanged} largest Networth *Unchanged* since past 12 hours**'
        unchanged_message = create_message(header_unchanged, self.get_unchanged_nw(top=nr_networth_unchanged))
        discord_message = f"{top10_message}\n{bot10_message}"

        logger.debug("Sending to Discord webhook: %s", discord_message)
        webhook_response = send_to_webhook(discord_message)
        logger.debug("Webhook response: %s", webhook_response)

        logger.debug("Sending to Discord webhook: %s", unchanged_message)
        webhook_response = send_to_webhook(unchanged_message)
        logger.debug("Webhook response: %s", webhook_response)

        return webhook_response

    # ---------------------------------------- QUERIES - Single Dominion

    def dominion(self, dom_code):
        return Dominion(self._db, dom_code)

    def dom_status(self, dom_code: int, update=False):
        """Get information of a specific dominion."""
        logger.debug("Getting dom status for %s", dom_code)
        if update:
            self.update_ops(dom_code)
        return query_clearsight(self._db, dom_code)

    def castle(self, dom_code):
        """Get the castle information of a specific dominion."""
        logger.debug("Getting Castle for %s", dom_code)
        return query_castle(self._db, dom_code)

    def barracks(self, dom_code):
        """Get the barracks information of a specific dominion."""
        logger.debug("Getting Barracks for %s", dom_code)
        return query_barracks(self._db, dom_code)

    def survey(self, dom_code, latest=False):
        """Get the survey information of a specific dominion."""
        logger.debug("Getting survey for %s", dom_code)
        return query_survey(self._db, dom_code, latest)

    def nw_history(self, dom_code):
        """Get the networth history of a specific dominion."""
        logger.debug("Getting NW history for %s", dom_code)
        return query_dom_history(self._db, dom_code)

    # ---------------------------------------- QUERIES - Lists

    def dom_list(self, since='-12 hours'):
        """Get overview information of all dominions."""
        logger.debug("Getting dom list with NW since %s", since)
        doms = all_doms(self._db)
        nw_deltas = get_networth_deltas(self._db, since)
        return sorted(doms, key=itemgetter('land'), reverse=True), nw_deltas

    def get_town_crier(self):
        logger.debug("Getting Town Crier")
        return query_town_crier(self._db)

    def doms_with_ratios(self):
        """Overview of the ratios of all dominions."""
        all_dom_codes = [d['code'] for d in all_doms(self._db)]
        result = list()
        for domcode in all_dom_codes:
            dom = Dominion(self._db, domcode)
            if str(dom.military.ratio_estimate) != 'Unknown':
                result.append(dom)
        return sorted(result, key=lambda d: d.military.ratio_estimate, reverse=True)

    def all_doms_as_objects(self):
        all_dom_codes = [d['code'] for d in all_doms(self._db)]
        result = list()
        for domcode in all_dom_codes:
            dom = Dominion(self._db, domcode)
            if (str(dom.military.op) != 'Unknown') or (str(dom.military.dp) != 'Unknown'):
                result.append(dom)
        return sorted(result, key=lambda d: d.networth, reverse=True)

    def all_doms_ops_age(self):
        last_ops = query_last_ops(self._db)
        return {op['code']: hours_since(op['last_op']) for op in last_ops}

    def top_op(self, dom_list=None):
        if not dom_list:
            dom_list = self.all_doms_as_objects()
        topop = dom_list[0]
        for dom in dom_list[1:]:
            dom_op = dom.military.max_sendable_op
            if not isinstance(dom_op, Unknown) and dom_op > topop.military.max_sendable_op:
                topop = dom
        return topop

    def realmie_codes(self) -> list[int]:
        logger.debug("Getting Realmies")
        realm = realm_of_dom(self._db, current_player_id)
        return dom_codes_of_realm(self._db, realm)

    def realmies(self) -> list[Dominion]:
        logger.debug("Getting Realmies")
        realm = realm_of_dom(self._db, current_player_id)
        return doms_of_realm(self._db, realm)

    def stealables(self) -> list:
        logger.debug("Listing stealables")
        since = add_duration(current_od_time(as_str=True), -12, True)
        result = query_stealables(self._db, since, realm_of_dom(self._db, current_player_id))
        return result

    # ---------------------------------------- QUERIES - Utility

    def name_for_dom_code(self, domcode):
        """Get the name connected with a dominion code."""
        logger.debug("Getting name for %s", domcode)
        return name_for_code(self._db, domcode)

    @property
    def current_tick(self):
        soup = get_soup_page(self.session, SEARCH_PAGE)
        return read_tick_time(soup)

    # ---------------------------------------- QUERIES - Reports

    def get_unchanged_nw(self, top: int = 50):
        logger.debug("Getting Unchanged NW")
        doms, nw_deltas = self.dom_list()
        selected_doms = [d for d, nwd in nw_deltas.items() if nwd == 0]
        relevant_doms = [d for d in doms if d['code'] in selected_doms]
        result = list()
        for row in relevant_doms:
            nw_row = {
                'code': row['code'],
                'name': row['name'],
                'land': row['land'],
                'networth': row['networth'],
                'nwdelta': nw_deltas[row['code']],
                'realm': row['realm']
            }
            result.append(nw_row)
        return sorted(result, key=itemgetter('land'), reverse=True)[:top]

    def get_top_bot_nw(self, top=True, filter_zeroes=False):
        logger.debug("Getting Top and Bot NW changes")
        doms, nw_deltas = self.dom_list()
        sorted_deltas = sorted(nw_deltas.items(), key=lambda x: x[1], reverse=top)[:10]
        selected_doms = [d[0] for d in sorted_deltas]
        relevant_doms = [d for d in doms if d['code'] in selected_doms]
        result = list()
        for row in relevant_doms:
            nw_row = {
                'code': row['code'],
                'name': row['name'],
                'land': row['land'],
                'networth': row['networth'],
                'nwdelta': nw_deltas[row['code']],
                'realm': row['realm']
            }
            result.append(nw_row)
        if filter_zeroes:
            result = [dom for dom in result if dom['nwdelta'] != 0]
        return sorted(result, key=itemgetter('nwdelta'), reverse=top)

    def economy(self):
        self.update_ops(current_player_id)
        return Economy(self.dominion(current_player_id))
