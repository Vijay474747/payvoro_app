package com.payvoro.app

import com.payvoro.app.service.PayerName
import org.junit.Assert.*
import org.junit.Test

/** Plus plan reads the customer's name out loud. Only real names may pass. Run: ./gradlew test */
class PayerNameTest {
    @Test fun capsNameIsTidied() = assertEquals("Ramesh Kumar", PayerName.clean("RAMESH KUMAR"))
    @Test fun longNameKeepsThreeWords() = assertEquals("Anitha Devi Ravi", PayerName.clean("anitha devi ravi kumar"))
    @Test fun phoneNumberIsDropped() = assertNull(PayerName.clean("9876543210"))
    @Test fun upiIdIsDropped() = assertNull(PayerName.clean("ramesh@okaxis"))
    @Test fun genericWordsAreDropped() {
        assertNull(PayerName.clean("UPI user"))
        assertNull(PayerName.clean("Customer"))
        assertNull(PayerName.clean("XXXX1234"))
    }
    @Test fun emptyIsDropped() {
        assertNull(PayerName.clean(null))
        assertNull(PayerName.clean(" "))
    }
}
