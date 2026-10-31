package com.payvoro.app

import com.payvoro.app.service.UpiQrParser
import org.junit.Assert.*
import org.junit.Test

class UpiQrParserTest {
    @Test fun upiLink() {
        val s = UpiQrParser.parse("upi://pay?pa=ravistores@okaxis&pn=Ravi%20Stores&mc=5411&mode=02&purpose=00")!!
        assertEquals("ravistores@okaxis", s.vpa)
        assertEquals("Ravi Stores", s.name)
        assertTrue(s.isUpiLink)
    }

    @Test fun upperCaseScheme() {
        assertEquals("shop@ybl", UpiQrParser.parse("UPI://pay?pa=shop@ybl&pn=Shop")!!.vpa)
    }

    @Test fun plainUpiId() {
        assertEquals("kumar.tea@paytm", UpiQrParser.parse(" kumar.tea@paytm ")!!.vpa)
    }

    @Test fun bharatQr() {
        // EMV TLV: tag 26 holds GUID + UPI ID, tag 59 holds the shop name
        val vpa = "kumartea@okicici"
        val sub = "0010A000000524" + "01" + "%02d".format(vpa.length) + vpa
        val emv = "000201" + "010211" + "26" + "%02d".format(sub.length) + sub + "5303356" + "5802IN" + "5909KUMAR TEA" + "6007CHENNAI" + "6304ABCD"
        val s = UpiQrParser.parse(emv)!!
        assertEquals("kumartea@okicici", s.vpa)
        assertEquals("KUMAR TEA", s.name)
    }

    @Test fun rejectsNonPayment() {
        assertNull(UpiQrParser.parse("https://example.com"))
        assertNull(UpiQrParser.parse("upi://pay?pn=NoId"))
        assertNull(UpiQrParser.parse("hello world"))
    }

    @Test fun amountKeepsOriginalFields() {
        val s = UpiQrParser.parse("upi://pay?pa=shop@okaxis&pn=Shop&mc=5411&am=10.00")!!
        val link = UpiQrParser.withAmount(s, "shop@okaxis", "Shop", 250.0)
        assertTrue(link.contains("mc=5411"))
        assertTrue(link.endsWith("am=250.00"))
        assertFalse(link.contains("am=10.00"))
        assertEquals(s.raw, UpiQrParser.withAmount(s, "shop@okaxis", "Shop", null))
    }
}
