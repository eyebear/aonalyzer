from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from app.options.manual_option_models import (
    EXPECTED_OPTION_FIELDS,
    ParsedManualOptionInput,
)


class ManualOptionTextParser:
    """
    Flexible parser for user-pasted option text.

    The parser accepts human language, copied table rows, broker text, and
    imperfect notes. It extracts only values that are visible in the text.
    It does not invent missing values.
    """

    MONTHS = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }

    def parse(
        self,
        raw_text: str,
        supplied_symbol: str | None = None,
        supplied_source_name: str | None = None,
    ) -> ParsedManualOptionInput:
        clean_text = raw_text.strip()
        normalized_text = self._normalize_text(clean_text)

        symbol = self._normalize_symbol(
            supplied_symbol
            or self._extract_symbol(normalized_text)
        )

        source_name = supplied_source_name or self._extract_source_name(clean_text)

        expiration_date = self._extract_expiration_date(normalized_text)
        option_type = self._extract_option_type(normalized_text)
        strike = self._extract_strike(normalized_text, option_type)

        bid, ask = self._extract_bid_ask(normalized_text)

        underlying_price = self._extract_underlying_price(normalized_text)
        last_price = self._extract_number_by_labels(
            normalized_text,
            labels=[
                "last price",
                "last traded",
                "last",
                "mark",
            ],
        )

        volume = self._extract_int_by_labels(
            normalized_text,
            labels=[
                "volume",
                "vol",
            ],
            excluded_following_words=["atility"],
        )

        open_interest = self._extract_int_by_labels(
            normalized_text,
            labels=[
                "open interest",
                "open int",
                "oi",
            ],
        )

        implied_volatility = self._extract_implied_volatility(normalized_text)

        delta = self._extract_number_by_labels(
            normalized_text,
            labels=[
                "delta",
                "Δ",
            ],
        )
        gamma = self._extract_number_by_labels(
            normalized_text,
            labels=[
                "gamma",
                "Γ",
            ],
        )
        theta = self._extract_number_by_labels(
            normalized_text,
            labels=[
                "theta",
                "Θ",
            ],
        )
        vega = self._extract_number_by_labels(
            normalized_text,
            labels=[
                "vega",
            ],
        )
        rho = self._extract_number_by_labels(
            normalized_text,
            labels=[
                "rho",
            ],
        )

        dte = self._calculate_dte(expiration_date)
        mid_price = self._calculate_mid_price(bid=bid, ask=ask)
        premium = mid_price if mid_price is not None else last_price
        spread_percent = self._calculate_spread_percent(
            bid=bid,
            ask=ask,
            mid_price=mid_price,
        )
        contract_cost = self._calculate_contract_cost(premium)
        breakeven = self._calculate_breakeven(
            option_type=option_type,
            strike=strike,
            premium=premium,
        )
        breakeven_distance = self._calculate_breakeven_distance(
            breakeven=breakeven,
            underlying_price=underlying_price,
        )
        breakeven_distance_percent = self._calculate_breakeven_distance_percent(
            breakeven_distance=breakeven_distance,
            underlying_price=underlying_price,
        )

        parsed_values: dict[str, Any] = {
            "symbol": symbol,
            "source_name": source_name,
            "underlying_price": underlying_price,
            "expiration_date": expiration_date.isoformat()
            if expiration_date
            else None,
            "option_type": option_type,
            "strike": strike,
            "bid": bid,
            "ask": ask,
            "last_price": last_price,
            "volume": volume,
            "open_interest": open_interest,
            "implied_volatility": implied_volatility,
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "rho": rho,
            "dte": dte,
            "mid_price": mid_price,
            "spread_percent": spread_percent,
            "contract_cost": contract_cost,
            "breakeven": breakeven,
            "breakeven_distance": breakeven_distance,
            "breakeven_distance_percent": breakeven_distance_percent,
        }

        parsed_fields = {
            key: value
            for key, value in parsed_values.items()
            if value is not None
        }

        missing_fields = [
            field
            for field in EXPECTED_OPTION_FIELDS
            if parsed_values.get(field) is None
        ]

        parser_confidence = self._calculate_parser_confidence(parsed_fields)
        data_quality_status = self._calculate_data_quality_status(parsed_fields)

        return ParsedManualOptionInput(
            raw_text=clean_text,
            symbol=symbol,
            source_name=source_name,
            underlying_price=underlying_price,
            expiration_date=expiration_date,
            option_type=option_type,
            strike=strike,
            bid=bid,
            ask=ask,
            last_price=last_price,
            volume=volume,
            open_interest=open_interest,
            implied_volatility=implied_volatility,
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            rho=rho,
            dte=dte,
            mid_price=mid_price,
            spread_percent=spread_percent,
            contract_cost=contract_cost,
            breakeven=breakeven,
            breakeven_distance=breakeven_distance,
            breakeven_distance_percent=breakeven_distance_percent,
            parser_confidence=parser_confidence,
            missing_fields=missing_fields,
            parsed_fields=parsed_fields,
            data_quality_status=data_quality_status,
            needs_ai_review=parser_confidence != "HIGH",
        )

    def _normalize_text(self, text: str) -> str:
        return (
            text.replace("\n", " ")
            .replace("\t", " ")
            .replace("×", "x")
            .replace("–", "-")
            .replace("—", "-")
            .replace("：", ":")
        )

    def _normalize_symbol(self, value: str | None) -> str | None:
        if value is None:
            return None

        clean_value = value.strip().upper()

        if not clean_value:
            return None

        return clean_value

    def _extract_symbol(self, text: str) -> str | None:
        month_names = "|".join(self.MONTHS.keys())

        explicit_patterns = [
            r"\b(?:ticker|symbol)\s*[:=]?\s*([A-Z]{1,6})(?:\b|\.|\s)",
            rf"\b([A-Z]{{1,6}})\s+(?:{month_names})\s+\d{{1,2}}\s+20\d{{2}}\b",
            r"\b([A-Z]{1,6})\s+\d{1,2}/\d{1,2}/\d{2,4}\b",
            r"\b([A-Z]{1,6})\s+\d{2,6}\s*[CP]\b",
            r"\b([A-Z]{1,6})\s+(?:option|options|call|put)\b",
            r"\b([A-Z]{1,6})\s+[A-Z]{3}\d{6}[CP]\d{5,8}\b",
        ]

        for pattern in explicit_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).upper()

        first_word_match = re.match(r"^\s*([A-Z]{1,6})\b", text)
        if first_word_match:
            candidate = first_word_match.group(1).upper()
            if candidate not in {"I", "THE", "A", "AN", "THIS", "THAT"}:
                if re.search(
                    r"\b(call|put|bid|ask|strike|iv|delta|theta|vega|gamma|oi|option)\b",
                    text,
                    flags=re.IGNORECASE,
                ):
                    return candidate

        return None

    def _extract_source_name(self, text: str) -> str | None:
        match = re.search(
            r"\bsource\s*[:=]\s*([A-Za-z0-9 ._\-/]+)",
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            return None

        value = match.group(1).strip()

        if not value:
            return None

        return value[:120]

    def _extract_expiration_date(self, text: str) -> date | None:
        iso_match = re.search(
            r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b",
            text,
        )
        if iso_match:
            return self._safe_date(
                year=int(iso_match.group(1)),
                month=int(iso_match.group(2)),
                day=int(iso_match.group(3)),
            )

        slash_match = re.search(
            r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b",
            text,
        )
        if slash_match:
            month = int(slash_match.group(1))
            day = int(slash_match.group(2))
            year = int(slash_match.group(3))

            if year < 100:
                year += 2000

            return self._safe_date(year=year, month=month, day=day)

        month_names = "|".join(self.MONTHS.keys())
        month_match = re.search(
            rf"\b({month_names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
            text,
            flags=re.IGNORECASE,
        )
        if month_match:
            month_name = month_match.group(1).lower()
            day = int(month_match.group(2))
            year = int(month_match.group(3))
            return self._safe_date(
                year=year,
                month=self.MONTHS[month_name],
                day=day,
            )

        return None

    def _safe_date(self, year: int, month: int, day: int) -> date | None:
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _extract_option_type(self, text: str) -> str | None:
        if re.search(r"\b(call|calls)\b", text, flags=re.IGNORECASE):
            return "CALL"

        if re.search(r"\b(put|puts)\b", text, flags=re.IGNORECASE):
            return "PUT"

        if re.search(r"\b[Cc]\s*\d{1,6}(?:\.\d+)?\b", text):
            return "CALL"

        if re.search(r"\b[Pp]\s*\d{1,6}(?:\.\d+)?\b", text):
            return "PUT"

        contract_symbol_pattern = re.search(
            r"\b[A-Z]{1,6}\d{6}([CP])\d{5,8}\b",
            text,
            flags=re.IGNORECASE,
        )
        if contract_symbol_pattern:
            code = contract_symbol_pattern.group(1).upper()
            return "CALL" if code == "C" else "PUT"

        return None

    def _extract_strike(self, text: str, option_type: str | None) -> float | None:
        value = self._extract_number_by_labels(
            text,
            labels=[
                "strike price",
                "strike",
            ],
        )

        if value is not None:
            return value

        if option_type == "CALL":
            c_match = re.search(r"\b[Cc]\s*(\d{1,6}(?:\.\d+)?)\b", text)
            if c_match:
                return self._to_float_or_none(c_match.group(1))

            call_match = re.search(
                r"\b(\d{1,6}(?:\.\d+)?)\s+(?:call|calls)\b",
                text,
                flags=re.IGNORECASE,
            )
            if call_match:
                return self._to_float_or_none(call_match.group(1))

        if option_type == "PUT":
            p_match = re.search(r"\b[Pp]\s*(\d{1,6}(?:\.\d+)?)\b", text)
            if p_match:
                return self._to_float_or_none(p_match.group(1))

            put_match = re.search(
                r"\b(\d{1,6}(?:\.\d+)?)\s+(?:put|puts)\b",
                text,
                flags=re.IGNORECASE,
            )
            if put_match:
                return self._to_float_or_none(put_match.group(1))

        contract_symbol_pattern = re.search(
            r"\b[A-Z]{1,6}\d{6}[CP](\d{5,8})\b",
            text,
            flags=re.IGNORECASE,
        )
        if contract_symbol_pattern:
            raw_strike = contract_symbol_pattern.group(1)
            try:
                return int(raw_strike) / 1000
            except ValueError:
                return None

        return None

    def _extract_bid_ask(self, text: str) -> tuple[float | None, float | None]:
        bid = self._extract_number_by_labels(text, labels=["bid"])
        ask = self._extract_number_by_labels(text, labels=["ask"])

        if bid is not None or ask is not None:
            return bid, ask

        spread_match = re.search(
            r"\b(\d+(?:\.\d+)?)\s*(?:x|X|by|to|-)\s*(\d+(?:\.\d+)?)\b",
            text,
        )
        if spread_match:
            first_value = self._to_float_or_none(spread_match.group(1))
            second_value = self._to_float_or_none(spread_match.group(2))
            return first_value, second_value

        return None, None

    def _extract_underlying_price(self, text: str) -> float | None:
        value = self._extract_number_by_labels(
            text,
            labels=[
                "underlying price",
                "current stock price",
                "stock price",
                "stock around",
                "stock is around",
                "stock is",
                "underlying",
            ],
        )

        if value is not None:
            return value

        around_match = re.search(
            r"\bstock\s+(?:around|near|at)\s+(\d+(?:\.\d+)?)\b",
            text,
            flags=re.IGNORECASE,
        )

        if around_match:
            return self._to_float_or_none(around_match.group(1))

        return None

    def _extract_implied_volatility(self, text: str) -> float | None:
        value = self._extract_number_by_labels(
            text,
            labels=[
                "implied volatility",
                "iv",
            ],
        )

        if value is None:
            return None

        nearby_percent = re.search(
            r"\b(?:implied volatility|iv)\s*(?:is|around|:|=)?\s*[-+]?\d+(?:\.\d+)?\s*%",
            text,
            flags=re.IGNORECASE,
        )

        if nearby_percent or value > 3:
            return value / 100

        return value

    def _extract_number_by_labels(
        self,
        text: str,
        labels: list[str],
    ) -> float | None:
        for label in labels:
            escaped_label = re.escape(label)
            pattern = (
                rf"\b{escaped_label}\b\s*"
                rf"(?:is|around|near|at|:|=)?\s*"
                rf"([-+]?(?:\d+(?:\.\d+)?|\.\d+))"
            )

            match = re.search(pattern, text, flags=re.IGNORECASE)

            if match:
                return self._to_float_or_none(match.group(1))

        return None

    def _extract_int_by_labels(
        self,
        text: str,
        labels: list[str],
        excluded_following_words: list[str] | None = None,
    ) -> int | None:
        excluded_following_words = excluded_following_words or []

        for label in labels:
            escaped_label = re.escape(label)
            negative_lookahead = ""
            if excluded_following_words:
                negative_lookahead = rf"(?!{'|'.join(excluded_following_words)})"

            pattern = (
                rf"\b{escaped_label}\b"
                rf"{negative_lookahead}"
                rf"\s*(?:is|around|near|at|:|=)?\s*"
                rf"(\d+(?:,\d{{3}})*|\d+)"
            )

            match = re.search(pattern, text, flags=re.IGNORECASE)

            if match:
                value = match.group(1).replace(",", "")
                return self._to_int_or_none(value)

        return None

    def _to_float_or_none(self, value: Any) -> float | None:
        if value is None:
            return None

        try:
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None

    def _to_int_or_none(self, value: Any) -> int | None:
        if value is None:
            return None

        try:
            return int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError):
            return None

    def _calculate_dte(self, expiration_date: date | None) -> int | None:
        if expiration_date is None:
            return None

        today = datetime.now(timezone.utc).date()
        return max((expiration_date - today).days, 0)

    def _calculate_mid_price(
        self,
        bid: float | None,
        ask: float | None,
    ) -> float | None:
        if bid is None or ask is None:
            return None

        if bid < 0 or ask < 0:
            return None

        return (bid + ask) / 2

    def _calculate_spread_percent(
        self,
        bid: float | None,
        ask: float | None,
        mid_price: float | None,
    ) -> float | None:
        if bid is None or ask is None or mid_price is None:
            return None

        if mid_price <= 0:
            return None

        return (ask - bid) / mid_price

    def _calculate_contract_cost(self, premium: float | None) -> float | None:
        if premium is None:
            return None

        return premium * 100

    def _calculate_breakeven(
        self,
        option_type: str | None,
        strike: float | None,
        premium: float | None,
    ) -> float | None:
        if option_type is None or strike is None or premium is None:
            return None

        if option_type == "CALL":
            return strike + premium

        if option_type == "PUT":
            return strike - premium

        return None

    def _calculate_breakeven_distance(
        self,
        breakeven: float | None,
        underlying_price: float | None,
    ) -> float | None:
        if breakeven is None or underlying_price is None:
            return None

        return breakeven - underlying_price

    def _calculate_breakeven_distance_percent(
        self,
        breakeven_distance: float | None,
        underlying_price: float | None,
    ) -> float | None:
        if breakeven_distance is None or underlying_price is None:
            return None

        if underlying_price == 0:
            return None

        return breakeven_distance / underlying_price

    def _calculate_parser_confidence(
        self,
        parsed_fields: dict[str, Any],
    ) -> str:
        core_fields = [
            "symbol",
            "expiration_date",
            "option_type",
            "strike",
        ]

        pricing_fields = [
            "bid",
            "ask",
            "last_price",
        ]

        core_count = sum(1 for field in core_fields if field in parsed_fields)
        pricing_count = sum(1 for field in pricing_fields if field in parsed_fields)

        if core_count == 4 and pricing_count >= 2:
            return "HIGH"

        if core_count >= 3 and pricing_count >= 1:
            return "MEDIUM"

        return "LOW"

    def _calculate_data_quality_status(
        self,
        parsed_fields: dict[str, Any],
    ) -> str:
        if not parsed_fields:
            return "OPTION_DATA_NOT_AVAILABLE"

        minimum_fields = [
            "symbol",
            "expiration_date",
            "option_type",
            "strike",
        ]

        has_minimum_fields = all(
            field in parsed_fields
            for field in minimum_fields
        )

        has_price_context = (
            "bid" in parsed_fields and "ask" in parsed_fields
        ) or "last_price" in parsed_fields

        if has_minimum_fields and has_price_context:
            return "OPTION_TEXT_PARSED"

        return "INSUFFICIENT_OPTION_DATA"