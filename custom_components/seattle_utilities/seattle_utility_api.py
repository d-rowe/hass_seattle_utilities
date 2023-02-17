import base64
import dataclasses
import json
import logging
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, date
from html.parser import HTMLParser
from typing import Tuple, Optional, Dict, Any, List

import requests

logging.basicConfig(stream=sys.stdout)


class OracleClient:
    ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    LOGGER = logging.getLogger(__name__)
    JS_ITEM_RE = re.compile(r"setItem\(['\"](.+?)['\"],\s?['\"](.+?)['\"]\);")

    class HTMLOracleFormParser(HTMLParser):
        def __init__(self):
            self.form_url = None
            self.form_data = {}
            self.name = None
            self.value = None
            super().__init__()

        def reset(self) -> None:
            super().reset()
            self.form_url = None
            self.form_data = {}
            self.name = None
            self.value = None

        def handle_starttag(self, tag, attrs):
            if tag == "form":
                for attr in attrs:
                    if attr[0] == "action":
                        self.form_url = attr[1]

            if tag == "input":
                for attr in attrs:
                    if "name" in attr:
                        self.name = attr[1]
                    if "value" in attr:
                        self.value = attr[1]

        def handle_endtag(self, tag):
            if tag != "input":
                return
            self.form_data[self.name] = self.value
            self.name = None
            self.value = None

        @property
        def form_info(self):
            return self.form_url, self.form_data

    def __init__(self, base_domain: str):
        self.base_domain = base_domain
        self._session = requests.Session()
        self._authentication_token_info = None
        self._token_expires = None

    @property
    def token_created_at(self) -> Optional[datetime]:
        if "created" not in self._authentication_token_info:
            return None
        return datetime.fromtimestamp(self._authentication_token_info.get("created") / 1000)

    @property
    def token_expires_in(self) -> Optional[timedelta]:
        if "expires_in" not in self._authentication_token_info:
            return timedelta(seconds=0)
        return timedelta(seconds=self._authentication_token_info.get("expires_in"))

    @property
    def is_token_expired(self):
        token_created_at = self.token_created_at
        if token_created_at is None:
            return True
        return datetime.now() - token_created_at >= self.token_expires_in

    def __get_location(self) -> str:
        headers = {"Accept": self.ACCEPT_HTML, "Host": self.base_domain}
        res = self._session.get(
            url=f"https://{self.base_domain}/rest/auth/ssologin",
            headers=headers,
            allow_redirects=False
        )
        res.raise_for_status()
        if "Location" not in res.headers:
            raise LookupError("Unable to locate Oracle Location")
        return res.headers.get("Location")

    def __get_oracle_identity(self) -> Dict[str, Any]:
        # Get Oracle Location
        self.LOGGER.debug("Requesting Oracle Location")
        oracle_location = self.__get_location()
        # Set Oracle Cookie
        self.LOGGER.debug("Requesting Oracle Cookie")
        oracle_cookie_res = self._session.get(
            url=oracle_location,
            headers={"Accept": self.ACCEPT_HTML},
            allow_redirects=False
        )
        oracle_cookie_res.raise_for_status()
        oracle_identity_url = oracle_cookie_res.headers.get("Location", None)
        # Get Oracle Identity
        self.LOGGER.debug("Requesting Oracle Identity")
        oracle_identity_res = self._session.get(
            url=oracle_identity_url,
            headers={"Accept": self.ACCEPT_HTML},
            allow_redirects=False
        )
        oracle_identity_res.raise_for_status()
        identity_parser = self.HTMLOracleFormParser()
        identity_parser.feed(oracle_identity_res.text)
        identity_url, identity_req_data = identity_parser.form_info
        # Get Oracle Identity
        self.LOGGER.debug("Requesting Oracle Identity Data")
        identity_res = self._session.post(
            url=identity_url,
            data=identity_req_data,
            allow_redirects=False
        )
        identity_res.raise_for_status()
        identity_data = dict(self.JS_ITEM_RE.findall(identity_res.text))
        identity_data.update({"initialState": json.loads(identity_data.get("initialState"))})
        return identity_data

    def __get_authentication_tokens(self, username: str, password: str, authentication_url: str,
                                    identity_data: Dict[str, Any]) -> Dict[str, str]:
        if authentication_url is None:
            authentication_url = f"https://{self.base_domain}/authenticate"
        authentication_req_data = {
            "credentials": {
                "password": password,
                "username": username,
            },
            "signinAT": identity_data.get("signinAT"),
            "initialState": identity_data.get("initialState")
        }
        self.LOGGER.debug("Requesting Authentication Tokens...")
        authentication_res = self._session.post(
            url=authentication_url,
            json=authentication_req_data,
            headers={"Content-Type": "application/json"},
            allow_redirects=False,
        )
        authentication_res.raise_for_status()
        return authentication_res.json()

    def __submit_form(self, url: str, data: Dict[str, str]) -> Tuple[Optional[str], str, Dict[str, Any]]:
        self.LOGGER.debug(f"Submitting form: {url}")
        res = self._session.post(url=url, data=data, allow_redirects=False)
        res.raise_for_status()
        parser = self.HTMLOracleFormParser()
        parser.feed(res.text)
        return res.headers.get("Location", None), parser.form_url, parser.form_data

    def login(self, username: str, password: str):
        self._login(username=username, password=password)

    def _login(self, username: str, password: str, authentication_url: str = None):
        try:
            identity_data = self.__get_oracle_identity()
            authentication_tokens = self.__get_authentication_tokens(
                username=username,
                password=password,
                authentication_url=authentication_url,
                identity_data=identity_data
            )
            session_url = urllib.parse.urljoin(identity_data.get("baseUri"), "sso/v1/sdk/session")
            session_req_data = {"authnToken": authentication_tokens.get("authnToken")}
            _, login_url, login_data = self.__submit_form(url=session_url, data=session_req_data)
            _, saml_url, saml_data = self.__submit_form(url=login_url, data=login_data)
            saml_loc, _, _ = self.__submit_form(url=saml_url, data=saml_data)
            _, usertoken = saml_loc.rsplit("/", 1)
            auth_token_req_data = {
                "usertoken": usertoken,
                "grant_type": "authorization_code",
                "logintype": "sso"
            }
            auth_token_bearer = base64.b64encode(b"webClientIdPassword:secret").decode("utf-8")
            auth_token_url = f"https://{self.base_domain}/rest/auth/token"
            self.LOGGER.debug(f"Requesting User Token Info")
            auth_token_res = self._session.post(
                url=auth_token_url,
                data=auth_token_req_data,
                headers={"Authorization": f"Basic {auth_token_bearer}"},
                allow_redirects=False,
            )
            auth_token_res.raise_for_status()
            self._authentication_token_info = auth_token_res.json()
        except Exception as e:
            self.LOGGER.exception("Failed to login to Seattle Utility")
            raise ConnectionRefusedError("Failed to login to Seattle Utility") from e

    @property
    def _access_token(self):
        if self._authentication_token_info is None:
            raise Exception("Authentication Token not set, please login.")
        return self._authentication_token_info.get("access_token", None)

    def request_payload(self, url_path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._access_token}"
        }
        url = urllib.parse.urljoin(f"https://{self.base_domain}", url_path)
        res = self._session.post(
            url=url,
            json=data,
            headers=headers,
            allow_redirects=False,
        )
        res.raise_for_status()
        return res.json()


@dataclasses.dataclass
class Account:
    account_number: str
    person_id: str
    service_address: str


@dataclasses.dataclass
class Bill:
    service_id: str
    meters: List[str]


@dataclasses.dataclass
class Meter:
    id: str
    account: Account
    bill: Bill


@dataclasses.dataclass
class MeterUsage:
    date: datetime
    usage_kWh: float
    cost: float = 0


@dataclasses.dataclass
class Rates:
    base: float = 0
    first_block: float = 0
    second_block: float = 0
    misc_per_kWh: float = 0


class SeattleUtilityClient(OracleClient):
    def __init__(self, rates: Rates = None):
        super().__init__(base_domain="myutilities.seattle.gov")
        self._rates = rates

    def login(self, username: str, password: str):
        self.LOGGER.info(f"Logging in...")
        super()._login(username=username, password=password,
                       authentication_url="https://login.seattle.gov/authenticate")

    @property
    def user_customer_id(self):
        if self._authentication_token_info is None:
            raise Exception("Authentication Token not set, please login.")
        return self._authentication_token_info.get("user", {}).get("customerId", None)

    @property
    def username(self):
        if self._authentication_token_info is None:
            raise Exception("Authentication Token not set, please login.")
        return self._authentication_token_info.get("user", {}).get("userName", None)

    def get_accounts(self) -> Dict[str, Any]:
        payload = {
            "customerId": self.user_customer_id,
            "csrId": self.username,
        }
        self.LOGGER.info(f"Looking up accounts.")
        return self.request_payload("rest/account/list", data=payload)

    def get_account_holders(self, company_code, page=1) -> Dict[str, Any]:
        payload = {
            "customerId": self.user_customer_id,
            "companyCode": company_code,
            "page": str(page),
            "account": [],
            "sortColumn": "DUED",
            "sortOrder": "DESC",
        }
        self.LOGGER.info(f"Looking up account holders.")
        return self.request_payload("rest/account/list/some", data=payload)

    def get_bills(self, company_code, account: Account, current_bill_date: Any) -> Dict[str, Any]:
        payload = {
            "customerId": self.user_customer_id,
            "accountContext": {
                "accountNumber": account.account_number,
                "personId": account.person_id,
                "companyCd": company_code,
                "serviceAddress": account.service_address,
            },
            "csrId": self.username,
            "type": "Consumption",
            "currentBillDate": current_bill_date,
            "period": "3",
        }
        self.LOGGER.info(f"Looking up bills for {account.account_number}.")
        return self.request_payload("rest/billing/comparison", data=payload)

    def get_daily_usage(self, meter: Meter, start: datetime, end: datetime):
        payload = {
            "customerId": self.user_customer_id,
            "accountContext": {
                "accountNumber": meter.account.account_number,
                "serviceId": meter.bill.service_id,
            },
            "startDate": start.strftime("%m/%d/%Y"),
            "endDate": end.strftime("%m/%d/%Y"),
            "port": meter.id,
        }
        self.LOGGER.info(f"Looking up daily usage for {meter.account.account_number}-{meter.id}.")
        daily_usage = self.request_payload("rest/usage/month", data=payload)
        daily_bill_usage = map(lambda day: MeterUsage(
            usage_kWh=float(day.get("billedConsumption")),
            date=datetime.strptime(day.get("chargeDateRaw"), "%Y-%m-%d"),
        ), daily_usage.get("history"))
        return list(filter(
            lambda usage: start <= usage.date <= end,
            map(self._estimate_usage_cost, daily_bill_usage)
        ))

    def get_meters(self) -> Dict[str, Meter]:
        meters = {}
        self.LOGGER.info("Looking up meters.")
        accounts = self.get_accounts()
        for group in accounts.get("accountGroups"):
            company_code = group.get("name")
            self.LOGGER.debug(f"Looking up account holders for: {group}")
            holders = self.get_account_holders(company_code=company_code)
            for holder_account in holders.get("account"):
                account = Account(
                    account_number=holder_account.get("accountNumber"),
                    person_id=holder_account.get("personId"),
                    service_address=holder_account.get("serviceAddress")
                )
                self.LOGGER.debug(f"Looking up bills for: {company_code}")
                current_bill_date = holder_account.get("currentBillDate")
                holder_bills = self.get_bills(
                    company_code=company_code,
                    account=account,
                    current_bill_date=current_bill_date,
                )
                for bill in holder_bills.get("billList"):
                    self.LOGGER.debug(f"Found bill: {bill}")
                    bill = Bill(service_id=bill.get("serviceId"), meters=bill.get("meters"))
                    for meter_id in bill.meters:
                        self.LOGGER.debug(f"Found meter: {meter_id}")
                        if meter_id in meters:
                            continue
                        meter = Meter(
                            id=meter_id,
                            account=account,
                            bill=bill
                        )
                        meters.update({meter_id: meter})
        return meters

    def get_latest_meter_usage(self, meter: Meter):
        today = datetime.combine(date.today(), datetime.max.time())
        yesterday = datetime.combine(date.today() - timedelta(days=1), datetime.min.time())
        daily_usage = self.get_daily_usage(
            meter=meter,
            start=yesterday,
            end=today,
        )
        return next(reversed([
            usage for usage in daily_usage
            if bool(usage.usage_kWh) and yesterday <= usage.date <= today
        ]), None)

    def get_latest_usage(self):
        meters = self.get_meters()
        return {
            meter_id: self.get_latest_meter_usage(meter=meter)
            for meter_id, meter in meters.items()
        }

    def _estimate_usage_cost(self, usage: MeterUsage):
        if self._rates is None:
            return 0
        # From https://seattle.gov/city-light/residential-services/billing-information/rates
        is_summer = 4 <= usage.date.month <= 9  # summer month (April - September)
        first_block_size = 10.0 if is_summer else 16.0  # In kWh
        first_block_usage = min(usage.usage_kWh, first_block_size)
        second_block_usage = max(0.0, usage.usage_kWh - first_block_size)
        first_block_usage_cost = self._rates.first_block * first_block_usage
        second_block_usage_cost = self._rates.second_block * second_block_usage
        misc_usage_cost = self._rates.misc_per_kWh * usage.usage_kWh
        total = sum([self._rates.base, first_block_usage_cost, second_block_usage_cost, misc_usage_cost])
        self.LOGGER.debug(" | ".join([
            f"Usage: {first_block_usage} + {second_block_usage} = {usage.usage_kWh}",
            f"Cost: {self._rates.base} + {first_block_usage_cost} + {second_block_usage_cost} + {misc_usage_cost} = {total}"
        ]))
        usage.cost = total
        return usage
