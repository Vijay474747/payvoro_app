package com.payvoro.app

import com.payvoro.app.service.NotificationParser
import org.junit.Assert.*
import org.junit.Test

/** Run: ./gradlew test   — add real notification texts from merchant phones here. */
class NotificationParserTest {
    @Test fun gpayReceived() {
        val p = NotificationParser.parse("Rahul Sharma paid you ₹500.00", "")!!
        assertEquals(500.0, p.amount, 0.0)
        assertEquals("Rahul Sharma", p.payer)
        assertEquals("SUCCESS", p.status)
    }
    @Test fun phonepeReceived() {
        val p = NotificationParser.parse("Received ₹1,250 from Priya K", "Money added to your bank account")!!
        assertEquals(1250.0, p.amount, 0.0)
        assertEquals("Priya K", p.payer)
    }
    @Test fun bankSmsCredit() {
        val p = NotificationParser.parse("AX-HDFCBK", "Rs.150.00 credited to a/c XX1234 on 25-10-26 by UPI ref 6293")!!
        assertEquals(150.0, p.amount, 0.0)
    }
    @Test fun ignoresOutgoing() {
        assertNull(NotificationParser.parse("You paid ₹200 to Ravi Stores", ""))
        assertNull(NotificationParser.parse("HDFC", "Rs 500 debited from a/c XX1234"))
    }
    @Test fun ignoresAdsAndRequests() {
        assertNull(NotificationParser.parse("Cashback received!", "You won ₹25 cashback"))
        assertNull(NotificationParser.parse("Ravi requested ₹300", "Pay now"))
    }
    @Test fun failed() {
        val p = NotificationParser.parse("Payment failed", "₹500 from Arun could not be received. Payment failed")!!
        assertEquals("FAILED", p.status)
    }
}
