import requests
from pprint import pprint
from login import username, password
from bs4 import BeautifulSoup
import re

TOWN_CRIER_URL = 'https://www.opendominion.net/dominion/town-crier'
LOGIN_URL = 'https://www.opendominion.net/auth/login'


def print_response(res: requests.Response):
    print(f"\n{res.url}\n")
    pprint(res.text)
    print("\n====================\n")


def login():
    session = requests.session()
    session.auth = (username, password)
    response = session.get(LOGIN_URL)
    # print_response(response)
    soup = BeautifulSoup(response.content, "html.parser")
    csrf_token = soup.select_one('meta[name="csrf-token"]')['content']
    payload = {
        '_token': csrf_token,
        'email': username,
        'password': password
    }
    response = session.post(LOGIN_URL, data=payload)
    if response.status_code == 200:
        return session
    else:
        print("Login Failed.")
        return None


def get_number_of_tc_pages(session):
    response = session.get(TOWN_CRIER_URL)
    # print_response(response)
    soup = BeautifulSoup(response.content, "html.parser")
    tc_page_urls = soup.find_all('a', href=re.compile(r'.*\/town-crier\?page=(\d+)'))
    page_numbers = [int(url['href'].split('page=')[-1]) for url in tc_page_urls]
    return max(page_numbers)


def get_tc_page(session, page_nr: int):
    def code_for_name(name):
        return event.find(string=re.compile(re.escape(name))).find_parent('a').attrs['href'].split('/')[-1]

    events = list()
    response = session.get(f'{TOWN_CRIER_URL}?page={page_nr}')
    # print_response(response)
    soup = BeautifulSoup(response.content, "html.parser")
    cs = soup.find('section', 'content')
    for row in cs.find_all('tr'):
        if not row.td.has_attr('colspan'):
            columns = row.find_all('td')
            timestamp = columns[0].span.string
            event = columns[1]
            dom_code = event.a.attrs['href'].split('/')[-1]
            dom_name = event.a.span.string
            event_text = ' '.join(event.stripped_strings)
            target_code = target_name = amount = ''
            if 'conquered' in event_text:
                event_type = 'invasion'
                target_name, amount = re.search(r'conquered (\d+) land from (.*) \(#', event_text).group(2, 1)
            elif 'invaded fellow dominion' in event_text:
                event_type = 'invasion'
                target_name, amount = re.search(r'invaded fellow dominion (.*) \(#\d+\) and captured (\d+)', event_text).group(1, 2)
            elif 'invaded' in event_text:
                event_type = 'invasion'
                target_name, amount = re.search(r'invaded (.*) \(#\d+\) and captured (\d+)', event_text).group(1, 2)
            elif 'fended off an attack' in event_text:
                event_type = 'bounce'
                target_name = re.search(r'.* fended off an attack from (.*) \(#', event_text).group(1)
            elif 'were beaten back by' in event_text:
                event_type = 'bounce'
                target_name = dom_name
                target_code = dom_code
                dom_name = re.search(r'Sadly, the forces of (.*) \(#\d+\) were beaten back by (.*) \(#', event_text).group(2)
                dom_code = code_for_name(dom_name)
            elif 'destroyed and rebuilt' in event_text:
                event_type = 'wonder_destruction'
                target_name, dom_name, dom_code = re.search(r'(.*) has been destroyed and rebuilt by (.*) \(#(\d+)', event_text).group(1, 2, 3)
                target_code = ' '
            elif 'has attacked' in event_text:
                event_type = 'wonder_attack'
                event_text = ' '.join([el.strip() for el in event_text.split('\n')])
                if 'a neutral wonder' in event_text:
                    target_name = 'a neutral wonder'
                    target_code = ' '
                else:
                    target_name, target_code = re.search(r'has attacked the (.*) \(#(\d+)', event_text).group(1, 2)
            elif 'CANCELED' in event_text:
                event_type = 'war_cancel'
                target_name, target_code = re.search(r'has CANCELED war against (.*) \(#(\d+)', event_text).group(1, 2)
            elif 'declared WAR' in event_text:
                event_type = 'war_declare'
                target_name, target_code = re.search(r'has declared WAR on (.*) \(#(\d+)', event_text).group(1, 2)
            else:
                event_type = 'other'

            if target_name and not target_code:
                if not event.find(string=re.compile(re.escape(target_name))):
                    raise Exception(f'Can not find "{target_name}" in {event}')
                target_code = event.find(string=re.compile(re.escape(target_name))).find_parent('a').attrs['href'].split('/')[-1]

            event_elements = [timestamp, event_type, dom_code, dom_name, target_code, target_name, amount, event_text]
            # list(event.children)
            events.append(event_elements)
    return events


if __name__ == '__main__':
    session = login()
    if session:
        with open('all_tc.txt', 'w') as f:
            for page_nr in range(1, get_number_of_tc_pages(session) + 1):
                events = get_tc_page(session, page_nr)
                for event in events:
                    event_line = f'''"{'", "'.join(event)}"'''
                    f.write(event_line)
                    f.write('\n')
                    print(event_line)
