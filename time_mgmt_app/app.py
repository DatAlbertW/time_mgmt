import streamlit as st
from datetime import datetime, timedelta
import random

# Fun and edgy calculator messages for each section

# Entry time messages
fun_messages_entry = [
    "Yo, you're finally here? Clock’s ticking, don’t act like you’re staying longer than you have to, bitch. 💪",
    "Look who decided to show up! Time to grind, but trust me, we’ll get you outta here real quick. 🏃",
    "Oh, you clocked in? Cool. Let’s make sure you don’t stick around here like a loser, bro. 😎",
    "You think this place deserves more of your time? Nah. Let's figure out when you can ghost this joint. 🚪",
    "Alright, you’re here. Big whoop. Let's plan your escape before they suck your soul out. 💀",
    "Another day in this dump. Let’s calculate how fast you can break outta here, alright? 💸",
    "Yo, you clocked in. Cool. But don’t get cozy, homie, this ain’t your crib. 🕓",
    "You're on the clock now, but that doesn't mean you gotta stick around. Let's bounce soon. ⏲️",
    "What’s up, champ? Don’t worry, we’ll figure out when you can get the hell outta here. 🕛",
    "Alright, my dude, you’re here. Now let’s find the quickest exit strategy. 🕐",
]

# Lunch start messages
fun_messages_lunch = [
    "Lunch already? Damn, don’t eat like a pig, fool. You still got work to pretend to do. 🍔",
    "Yo, it's lunch! Eat fast, don’t act like you're on some gourmet vacation. Get back, pronto. 🌮",
    "Oh, lunch break? Better not take too long, or they’ll think you’re MIA, you slacker. ⏳",
    "Time for chow, huh? Don’t overdo it – they’re not paying you for a 3-course meal, dawg. 🍕",
    "Lunch time, huh? Make it quick, fool. Ain’t nobody got time for you to take a nap afterward. 😴",
    "Bro, keep it light at lunch – I don’t wanna hear you whining about feeling bloated later. 🥪",
    "Take your break, eat, but don’t be dragging your ass back here like you ran a marathon, aight? 🍜",
    "Yo, lunch? Cool. Just don’t act like you’re clocked out for the day. Clock’s still ticking. ⏲️",
    "Grab a bite, but if you think you’re chilling here all afternoon, you're dead wrong. 🍱",
    "Don’t get comfy with that lunch. This ain’t a 5-star hotel. Eat up and get back to it. 🍔",
]

# After lunch messages
after_lunch_messages = [
    "Lunch is over, my dude. Time to get back to the grind. No more slacking! 🕛",
    "Lunch break's done, champ. Clock’s ticking, let's finish strong. 🍽️",
    "Hope you enjoyed that break. Time to get back and pretend to work again. 😜",
    "Alright, enough slacking. Lunch is over. Let’s finish this day without falling asleep, alright? 💤",
    "Lunch break is over, homie! Now, back to the grind like a true hustler. 💼",
    "Lunch break’s done, bro. Time to earn that paycheck... well, sorta. 🏢",
    "Yo, break's over! Clock's still ticking. Time to finish what you started. 🕛",
    "Lunch break done? Good. Now pretend like you’re busy until the end of the day. 📅",
    "No more chillin’, let’s get this day over with. Lunch is history, clock’s still running. ⏳",
    "Hope you didn’t eat too much. You still gotta make it through the day without falling asleep! 😴",
]

# Leave messages
fun_messages_leave = [
    "Yo, it’s quittin’ time, bitch! Get out before they trap you with more BS! 🏃‍♂️",
    "Clock out and run for it, fool! Don’t let ‘em catch you slipping. 🏡",
    "You’re free, champ! Time to dip before they realize you didn’t do sh*t all day. 😜",
    "Finally! Go home, drink something strong, and forget this place exists. 🎉",
    "It’s quittin’ time, mofo! Time to vanish like you got a warrant out. 🏃",
    "You’re still here? Nah, homie, get your ass out before they dump more work on you. 🚪",
    "Survived another day, huh? Get out, ninja style, before they even know you’re gone. 🐢",
    "You’ve done your time, homie. Now disappear before they reel you back in with more crap. 🕊️",
    "Alright, you made it. Bounce before they hit you with that ‘just one more thing’. 🧳",
    "Run, fool, run! It’s time to go ghost before they start asking questions. 👻",
]

# Final messages (for after work is fully completed)
fun_messages_final = [
    "Yo, you’re done! Go home, sit your ass down, and chill, my dude. 🏡",
    "That’s it, champ. You put in the time, now go grab a drink and forget about this place. 🍻",
    "You survived, and now it’s time to go home and pretend this day never happened. 😏",
    "Alright, tiger, you did your thing. Now bounce before they change their mind. 😂",
    "What the hell are you still doing here? You’re not earning extra brownie points, so GTFO! 🏆",
    "Congrats, hustler. Now get out before they change the rules on you and you’re stuck here. 🏃",
    "Wrap it up, chief. Grab yourself a beer and crash – you’ve earned it, kinda. 🍺",
    "And that’s a wrap, bro. Now go binge something dumb on Netflix. 📺",
    "You done, superhero? Cool. Now go home and do absolutely nothing. You deserve it. 🦸",
    "Yo, the day’s over. Go disappear for the night. This place ain’t worth thinking about. 🌃",
]

# Function to calculate leave time
def calculate_leave_time(entry_time, start_lunch=None, end_lunch=None, leave_time=None):
    workday_duration = timedelta(hours=8)
    
    if start_lunch and end_lunch:
        total_lunch_time = end_lunch - start_lunch
        lunch_duration_str = f"{total_lunch_time.seconds//3600}:{(total_lunch_time.seconds//60)%60:02d} hours"
    else:
        total_lunch_time = timedelta(0)
        lunch_duration_str = "00:00"

    # First input: Only entry time is provided
    if start_lunch is None:
        leave_time_30min = entry_time + workday_duration + timedelta(minutes=30)
        leave_time_1hr = entry_time + workday_duration + timedelta(hours=1)
        st.write(random.choice(fun_messages_entry))
        st.write(f"📅 With a 30 min lunch, you can leave at: **{leave_time_30min.strftime('%H:%M:%S')}**.")
        st.write(f"📅 With a 1 hour lunch, you can leave at: **{leave_time_1hr.strftime('%H:%M:%S')}**.")
    
    # Second input: Start lunch is provided, but not the end lunch time
    elif end_lunch is None:
        time_worked_until_lunch = start_lunch - entry_time
        leave_time_30min = start_lunch + workday_duration - time_worked_until_lunch + timedelta(minutes=30)
        leave_time_1hr = start_lunch + workday_duration - time_worked_until_lunch + timedelta(hours=1)
        st.write(random.choice(fun_messages_lunch))
        st.write(f"⏳ You’ve worked for: **{time_worked_until_lunch}** hours so far.")
        st.write(f"📅 With a 30 min lunch, you can leave at: **{leave_time_30min.strftime('%H:%M:%S')}**.")
        st.write(f"📅 With a 1 hour lunch, you can leave at: **{leave_time_1hr.strftime('%H:%M:%S')}**.")
        
    # Third input: End lunch time is provided (show after-lunch messages)
    elif end_lunch and leave_time is None:
        total_time_worked = start_lunch - entry_time  # time before lunch
        remaining_work_time = workday_duration - total_time_worked
        leave_time = end_lunch + remaining_work_time

        if remaining_work_time.total_seconds() > 0:
            hours_left = remaining_work_time.total_seconds() // 3600
            minutes_left = (remaining_work_time.total_seconds() % 3600) // 60
            
            st.write(random.choice(after_lunch_messages))
            st.write(f"📅 You had a {lunch_duration_str} lunch, you can leave at: **{leave_time.strftime('%H:%M:%S')}**.")
            st.write(f"⏳ You have **{int(hours_left)} hours and {int(minutes_left)} minutes** left.")
        else:
            st.write("Yo! You’re cutting it short! Cover that time tomorrow, or you’re gonna hear about it. ⏳")
    
    # Fourth input: Leave time is provided (final message and hours worked)
    if leave_time:
        total_time_worked = leave_time - entry_time - total_lunch_time
        if total_time_worked >= timedelta(hours=8):
            st.write(f"⏳ Total work hours (excluding lunch): **{total_time_worked}**.")
            st.write(random.choice(fun_messages_final))
        else:
            st.write("Yo! You’re cutting it short! Cover that time tomorrow, or you’re gonna hear about it. ⏳")

# App interface
st.title("🎯 Workday Calculator 🎯")
st.subheader("Calculate your leave time and get some real talk, fool. 😎")

# Input fields
entry_time_str = st.text_input("Enter your entry time (HH:MM:SS)", "")
start_lunch_str = st.text_input("Enter the start of your lunch time (HH:MM:SS, optional)", "")
end_lunch_str = st.text_input("Enter the end of your lunch time (HH:MM:SS, optional)", "")
leave_time_str = st.text_input("Enter your actual leave time (HH:MM:SS, optional)", "")

# Convert inputs to datetime
try:
    entry_time = datetime.strptime(entry_time_str, "%H:%M:%S") if entry_time_str else None
    start_lunch = datetime.strptime(start_lunch_str, "%H:%M:%S") if start_lunch_str else None
    end_lunch = datetime.strptime(end_lunch_str, "%H:%M:%S") if end_lunch_str else None
    leave_time = datetime.strptime(leave_time_str, "%H:%M:%S") if leave_time_str else None
except ValueError:
    st.error("Invalid time format. Please use HH:MM:SS")

# Perform calculations based on input
if entry_time:
    calculate_leave_time(entry_time, start_lunch, end_lunch, leave_time)
else:
    st.write("Yo! Give me your entry time, at least, you slacker!")
