from openai import OpenAI, RateLimitError
import json
import time


# OpenAI configuration
client = OpenAI()


def extract_booking_data_from_html(html):

    prompt = """
    Analyze the provided HTML concisely and extract these fields:

        - client_name: The Text under id "client-name" in the anchor 'a' tag.
        - booking_id: The series of numbers beside "Booking #".
        - workout_type: Text like "Stretch" or "Intro One on One" or similar under class "booking-title".
        - flexologist_name: Text under "Instructor" or, if unavailable, under "Added By".
        - phone: The Text under id "selected-phone-button" in the 'button' tag.
        - booking_time: The time of the booking in the under the class "time-value" in the "span" tag.
        Set field to "N/A" if not found. Return a JSON object with these exact field names. Here is the HTML:

    {html}
    """

    max_retries = 3
    retry_delay = 8

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You’re a data extractor that always returns JSON.",
                    },
                    {"role": "user", "content": prompt.format(html=html)},
                ],
                temperature=0,
            )
            result = response.choices[0].message.content
            if not isinstance(result, str):
                raise ValueError("Response content is not a string")

            cleaned_result = result.strip()
            if cleaned_result.startswith("```json"):
                cleaned_result = cleaned_result[7:-3].strip()

            data = json.loads(cleaned_result)
            return data

        except RateLimitError as e:
            print(f"Rate limit error: {e}")
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2**attempt)
                print(f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                print("Max retries reached")
                break
        except Exception as e:
            print(f"OpenAI error: {e}")
            break
    data = {
        "client_name": "Could not process",
        "member_rep_name": "Could not process",
        "flexologist_name": "Could not process",
        "status": "Could not process",
        "booking_date": "Could not process",
    }

    return data


def scrutinize_notes(notes, active):
    with open("api/ai/context.txt", "r") as file:
        context = file.read()

    if active == "YES":
        extra = ""
    else:
        extra = "6. Membership Recommendation: Recommends whether the client should continue, upgrade, or adjust their membership based on their progress, needs, or goals."

    prompt = """
    - This is the context:
    {context}

    - Input Notes:
    {notes}

    Analyze the provided notes to determine if they meet the requirements for a high-quality note, as outlined below. Follow these steps for each requirement to ensure no details are missed:

    1. **Verify Presence**: Check if the information is explicitly stated (e.g., "completed MAPS assessment"), implicitly provided (e.g., 'knots' as tightness, 'stress' as a reason for tension), or completely absent. Use the provided context to interpret abbreviations (e.g., 'PNF' as Proprioceptive Neuromuscular Facilitation, 'HF' as hip flexors, 'hammies' as hamstrings, 'HW' as homework) and terms (e.g., 'tight spots' as imbalances).
    2. **Assess Sufficiency**: Consider partial or implicit information sufficient unless the requirement explicitly demands a clear statement (e.g., a reason for no homework). For homework, if no tasks or reason for not assigning them is mentioned, treat it as missing.
    3. **Generate Questions**: Create a concise, non-redundant question only for requirements that are completely missing or unclear. Avoid questions for requirements with partial or implicit information (e.g., a list of muscle groups for the next session).

    Return a JSON object with a single field, "questions", containing a list of questions (strings). If all requirements are met, return an empty list ([]). Thoroughly review the context and notes before generating questions to ensure accurate interpretation of all details.

    - Requirements for a Quality Note:
    1. MAPS Assessment: Confirms that the Mobility, Activation, Posture, and Symmetry (MAPS) assessment was done or reviewed, or explicitly notes an exemption (e.g., due to injury, disability, or client condition).
    2. Actions Taken: Describes the stretching techniques (e.g., PNF, static, dynamic), muscle groups targeted, or exercises performed, including any details like duration, cycles, or range of motion (ROM).
    3. Purpose: States or implies the goals or reasons for the actions, such as reducing tightness, improving flexibility, addressing imbalances, or managing pain/stress, as defined in the context.
    4. Next Session Plan: Lists specific muscle groups, techniques, or periodization phase (e.g., Foundation, Active, Performance) planned for the next session.
    5. Homework: Specifies any stretching or mobility tasks assigned to the client, or provides a clear reason why no homework was assigned (e.g., lack of time, client preference). If neither tasks nor a reason is mentioned, consider this requirement unmet.
    {extra}


    """
    max_retries = 3
    retry_delay = 8

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="ft:gpt-4o-mini-2024-07-18:studio-hr::BcAAhLK9",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a note scrutinizer that analyzes fitness notes and always returns valid JSON output, formatted as specified, with no extra text, code blocks, or comments. Ensure the response is a valid JSON object with a single 'questions' field containing a list of strings.",
                    },
                    {
                        "role": "user",
                        "content": prompt.format(
                            context=context, notes=notes, extra=extra
                        ),
                    },
                ],
                temperature=0,
            )
            result = response.choices[0].message.content
            if not isinstance(result, str):
                raise ValueError("Response content is not a string")

            cleaned_result = result.strip()
            if cleaned_result.startswith("```json"):
                cleaned_result = cleaned_result[7:-3].strip()

            data = json.loads(cleaned_result)
            return data

        except RateLimitError as e:
            print(f"Rate limit error: {e}")
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2**attempt)
                print(f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                print("Max retries reached")
                break
        except Exception as e:
            print(f"OpenAI error: {e}")
            break
    data = {"questions": ["No questions found error"]}

    return data


def format_notes(notes):

    prompt = """
    The notes:
    {notes}

     Organize StretchLab Flexologist session notes into a structured and concise format following the SOAP note style commonly used in physical therapy. Focus on detailing what actions were taken during the session, why they were performed, and future plans. Ensure to exclude any 'Meeting Summary' details such as client name, Flexologist, or location. Highlight any missing information and provide suggestions for improvement in note-taking, if necessary.
      # Steps:
      1. What was done in the session:
         - Identify the current phase of periodization (e.g., month/week).
         - Describe the work being done within that phase, including variables and focus areas.
         - Provide MAPS scan results with interpretation related to goals and the current phase of periodization.
      2. Why the actions were performed:
         - Explain the reasoning behind the techniques used, such as addressing muscle guarding or enhancing tissue tolerance.
      3. Future plans:
         - Outline plans for the next session.
         - Include homework assignments, such as specific exercise videos or in-person demonstrations.
         - Suggest any relevant lifestyle changes or new activities.
      4. Identify and Highlight Missing Information:
         - Note any gaps in the provided session notes.
      5. Suggestions for Improvement:
         - Offer brief suggestions to enhance the quality of note-taking by the Flexologist.
      # Output Format:
        Return a JSON object with a single field, "notes", which is an array containing the formatted note objects i.e Current phase, Focus, MAPS, Next session, Homework, Considerations, Missing Information, and Suggestions. if any of the fields are missing, return "N/A" for that field. 

      # here is an example of a formatted note. Strictly adhere to the format provided:
        **Next session**: Focus on shoulders, hip, and abductor regions to address tightness identified in this session.
        **Current phase**: Active phase
        **MAPS**: Composite 48, Mobility 44, Activation 55, Posture 59, Symmetry 48. Indicates moderate mobility limitations, especially in shoulders and hip region, correlating with client's goals of increasing flexibility and mobility due to prolonged sitting.
        **Focus**: Full body flexibility and mobility improvement 
        **Homework**: Assigned shoulder and doorway stretches. Recommend practicing these daily to enhance shoulder mobility and alleviate tightness. Consider suggesting specific resources or videos for guidance.
        **Considerations**: Ayesha's long hours at the computer may contribute to her shoulder tension; discussing ergonomic adjustments or breaks during work hours could be beneficial in future sessions.
        **Excluded**:
        -
        **Suggested Improvement**:
        Consider providing more detailed observations of each stretch's effectiveness and any specific feedback from the client regarding comfort or difficulty.
    

    """
    max_retries = 3
    retry_delay = 8

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a note formatter that formats notes into a structured and concise format following the format provided in the example. Focus on detailing what actions were taken during the session, why they were performed, and future plans. Ensure to exclude any 'Meeting Summary' details such as client name, Flexologist, or location. Highlight any missing information and provide suggestions for improvement in note-taking, if necessary.",
                    },
                    {
                        "role": "user",
                        "content": prompt.format(notes=notes),
                    },
                ],
                temperature=0,
            )
            result = response.choices[0].message.content
            if not isinstance(result, str):
                raise ValueError("Response content is not a string")

            cleaned_result = result.strip()
            if cleaned_result.startswith("```json"):
                cleaned_result = cleaned_result[7:-3].strip()

            data = json.loads(cleaned_result)

            return data

        except RateLimitError as e:
            print(f"Rate limit error: {e}")
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2**attempt)
                print(f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                print("Max retries reached")
                break
        except Exception as e:
            print(f"OpenAI error: {e}")
            break
    data = {"notes": ["No notes formatted error"]}

    return data
