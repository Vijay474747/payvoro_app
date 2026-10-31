package com.payvoro.app

import com.payvoro.app.service.BankSmsFilter
import org.junit.Assert.*
import org.junit.Test

class BankSmsFilterTest {
    // ---- sender check ----
    @Test fun acceptsBankHeaders() {
        assertEquals("HDFCBK", BankSmsFilter.parseHeader("JD-HDFCBK-T")!!.brand)
        assertEquals("T", BankSmsFilter.parseHeader("JD-HDFCBK-T")!!.suffix)
        assertEquals("SBIUPI", BankSmsFilter.parseHeader("AX-SBIUPI")!!.brand)
        assertEquals("ICICIB", BankSmsFilter.parseHeader("ICICIB")!!.brand)
    }

    @Test fun rejectsPhoneNumbersAndNames() {
        assertNull(BankSmsFilter.parseHeader("+91 98400 12345"))
        assertNull(BankSmsFilter.parseHeader("9840012345"))
        assertNull(BankSmsFilter.parseHeader("Ravi Kumar"))
        assertNull(BankSmsFilter.parseHeader("Amma"))
    }

    @Test fun promotionalSuffixIsVisible() {
        assertEquals("P", BankSmsFilter.parseHeader("VM-HDFCBK-P")!!.suffix)
    }

    // ---- real credit SMS ----
    @Test fun hdfcCredit() {
        val c = BankSmsFilter.parseCredit(
            "Money Received - INR 500.00 in your HDFC Bank A/c xx1234 on 25-10-26 by A/c linked to VPA rahul@okaxis (UPI Ref No 629812345678)", "1234")!!
        assertEquals(500.0, c.amount, 0.0)
        assertEquals("629812345678", c.utr)
        assertEquals("rahul@okaxis", c.fromVpa)
    }

    @Test fun sbiCreditWithoutSpace() {
        val c = BankSmsFilter.parseCredit(
            "Dear SBI User, your A/cX1234-credited by Rs.150 on 25Oct26 transfer from RAHUL Ref No 629812345679 -SBI", "1234")!!
        assertEquals(150.0, c.amount, 0.0)
    }

    @Test fun iciciThreeDigitTail() {
        val c = BankSmsFilter.parseCredit(
            "Dear Customer, Acct XX234 is credited with Rs 75.00 on 25-Oct-26 from suresh@ybl. UPI:629812345670-ICICI Bank.", "1234")!!
        assertEquals(75.0, c.amount, 0.0)
    }

    // ---- must be rejected ----
    @Test fun wrongAccount() {
        assertNull(BankSmsFilter.parseCredit("Rs 500 credited to A/c XX9999 on 25-10-26 UPI Ref 629812345678", "1234"))
    }

    @Test fun debitMessages() {
        assertNull(BankSmsFilter.parseCredit("Sent Rs.500 From HDFC Bank A/C x1234 To Ravi On 25/10/26 Ref 629812345678", "1234"))
        assertNull(BankSmsFilter.parseCredit("A/c XX1234 debited by Rs 200 on 25-10-26; credited to ravi@okaxis", "1234"))
    }

    @Test fun spamAndFuture() {
        assertNull(BankSmsFilter.parseCredit("Rs 5000 credited to your account XX1234! Claim now http://bit.ly/x", null))
        assertNull(BankSmsFilter.parseCredit("Refund of Rs 300 will be credited to your A/c XX1234 in 5-7 days", "1234"))
        assertNull(BankSmsFilter.parseCredit("Pre-approved loan of Rs 2,00,000 credited instantly to A/c XX1234", null))
    }

    @Test fun noAccountMention() {
        assertNull(BankSmsFilter.parseCredit("Rs 500 credited. Thank you", null))
    }
}
