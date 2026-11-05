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

    // ---- v1.0.2: words inside names must not block a real payment ----
    @Test fun nameContainingBlockedWord() {
        assertNotNull(NotificationParser.parse("Hemitha paid you ₹10", ""))           // "emi" inside a name
        assertNotNull(NotificationParser.parse("Received ₹250 from Premium Stores", "")) // "emi" inside "Premium"
        assertNotNull(NotificationParser.parse("Ramesh Gloan paid you ₹40", ""))        // "loan" inside a word
        assertNotNull(NotificationParser.parse("Received ₹99 from Swinesh", ""))         // "win" inside a name
        assertNotNull(NotificationParser.parse("₹75 received from Rotpa", ""))           // "otp" inside a name
    }
    @Test fun paidToYourBankIsStillIncoming() {
        val p = NotificationParser.parse("Ramesh paid you ₹10", "Paid to your bank account XX1234")!!
        assertEquals(10.0, p.amount, 0.0)
        assertEquals("Ramesh", p.payer)
        assertNotNull(NotificationParser.parse("₹20 received from Anu", "Sent to your bank account"))
    }
    @Test fun stillBlocksRealAdsAndOutgoing() {
        assertNull(NotificationParser.parse("Pay your EMI of ₹2,000", "Loan reminder"))
        assertNull(NotificationParser.parse("Get a loan of ₹50,000", "received instantly"))
        assertNull(NotificationParser.parse("Ravi requested ₹300", "Pay now"))
        assertNull(NotificationParser.parse("You paid ₹200", "Paid to Ravi Stores"))
        assertNull(NotificationParser.parse("₹50 sent to Kumar", "Payment received by Kumar"))
        assertNull(NotificationParser.parse("Your OTP for ₹100 received", ""))
        assertNull(NotificationParser.parse("Refund of ₹100 received", ""))
    }
    @Test fun paytmAndPhonePeStyles() {
        assertEquals(10.0, NotificationParser.parse("Payment Received", "Received ₹10 from RAMESH KUMAR")!!.amount, 0.0)
        assertEquals(1.0, NotificationParser.parse("₹1 received", "from Suresh on PhonePe")!!.amount, 0.0)
        assertEquals(5.5, NotificationParser.parse("Rs. 5.50 credited", "Money added to your account")!!.amount, 0.0)
    }
}
