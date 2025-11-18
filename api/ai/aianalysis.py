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
        extra = "5. Membership Recommendation: Recommends whether the client should continue, upgrade, or adjust their membership based on their progress, needs, or goals."

    prompt = """
    - This is the context:
    {context}

    - Input Notes:
    {notes}

    Analyze the provided notes to determine if they meet the requirements for a high-quality note, as outlined below. Follow these steps for each requirement to ensure no details are missed:

    1. **Verify Presence**: Check if the information is explicitly stated (e.g., "2-3 PNF on shoulders"), implicitly provided (e.g., 'knots' as tightness, 'stress' as a reason for tension), or completely absent. Use the provided context to interpret abbreviations (e.g., 'PNF' as Proprioceptive Neuromuscular Facilitation, 'HF' as hip flexors, 'hammies' as hamstrings, 'HW' as homework) and terms (e.g., 'tight spots' as imbalances).
    2. **Assess Sufficiency**: Consider partial or implicit information sufficient unless the requirement explicitly demands a clear statement (e.g., a reason for no homework). For homework, if no tasks or reason for not assigning them is mentioned, treat it as missing.
    3. **Generate Questions**: Create a concise, non-redundant question only for requirements that are completely missing or unclear. Avoid questions for requirements with partial or implicit information (e.g., a list of muscle groups for the next session). Do not ask any Question regarding MAPS

    Return a JSON object with a single field, "questions", containing a list of questions (strings). If all requirements are met, return an empty list ([]). Thoroughly review the context and notes before generating questions to ensure accurate interpretation of all details.

    - Requirements for a Quality Note:
    1. Actions Taken: Describes the stretching techniques (e.g., PNF, static, dynamic), muscle groups targeted, or exercises performed, including any details like duration, cycles, or range of motion (ROM).
    2. Purpose: States or implies the goals or reasons for the actions, such as reducing tightness, improving flexibility, addressing imbalances, or managing pain/stress, as defined in the context.
    3. Next Session Plan: Lists specific muscle groups, techniques, or periodization phase (e.g., Foundation, Active, Performance) planned for the next session.
    4. Homework: Specifies any stretching or mobility tasks assigned to the client, or provides a clear reason why no homework was assigned (e.g., lack of time, client preference). If neither tasks nor a reason is mentioned, consider this requirement unmet.
    {extra}


    """
    max_retries = 3
    retry_delay = 8

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                # model="ft:gpt-4o-mini-2024-07-18:studio-hr::BmdJ6YQJ",
                model="ft:gpt-4o-mini-2024-07-18:studio-hr::BmhbGA6R",
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
    with open("api/ai/context.txt", "r") as file:
        context = file.read()

    prompt = """
     - This is the context:
    {context}

    - The notes:
    {notes}

     Organize StretchLab Flexologist session notes into a structured and concise format following the SOAP note style commonly used in physical therapy. Focus on detailing what actions were taken during the session, why they were performed, and future plans. Ensure to exclude any 'Meeting Summary' details such as client name, Flexologist, or location. Highlight any missing information and provide suggestions for improvement in note-taking, if necessary.
      # Steps:
      1. What was done in the session:
         - Identify the phase of periodization. Foundation phase is Foundation, Active phase is Active, Performance phase is Performance
         - Describe the work being done within that phase, including variables and focus areas.
         - Class is the session number or the class number or the logging number.
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
        Return a JSON object with a single field, "notes", which is an array containing the formatted note objects i.e Class (if mentioned), Phase (if mentioned), Maps (if mentioned), Today, Next, PNF (if mentioned), Homework (if mentioned), Details, Recommendation (if mentioned), Considerations, Missing Information and Suggestions

      # here is an example of a formatted note. Strictly adhere to the format provided:
        **Class**: 23 or Session #26 [if class is not mentioned, do not include it in JSON output]
        **Maps**: Maps score 38, or something like "Composite 48, Mobility 44, Activation  55, Posture 59, Symmetry 48"- this structure is also Maps. Check the context to get more information[if any information about maps is not mentioned, do not include it in JSON output]
        **Phase**: Active [if phase is not mentioned, do not include it in JSON output]
        **Today**: Full body flexibility and mobility improvement 
        **Next**: Focus on shoulders, hip, and abductor regions to address tightness identified in this session.
        **PNF**: 2-3 PNF or PNF 2-3
        **Homework**: Assigned shoulder and doorway stretches. Recommend practicing these daily to enhance shoulder mobility and alleviate tightness. Consider suggesting specific resources or videos for guidance. [if homework is not mentioned, do not include it in JSON output]
        **Details**: This is the details of the notes. Capturing all the intricacies of the note - the client's conversation, discussions during the session, reasons and other information stated, MAPS and other information, it should emcompass the inner detail of the session; keeping the tone
        **Recommendation**: 4x50 or 4x25 minutes, or some sort of recommendation [if not provided, do not include it in JSON output]
        **Considerations**: Ayesha's long hours at the computer may contribute to her shoulder tension; discussing ergonomic adjustments or breaks during work hours could be beneficial in future sessions.[if not provided, do not include it in JSON output]
        **Missing Information**:The Class, Phase, what was done in the session and next plan were not mentioned
        
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
                        "content": prompt.format(context=context,notes=notes),
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


# def format_notes(notes):

#     prompt = f"""
#     The notes:
#     {notes}

#     Organize the StretchLab Flexologist session notes into a structured yet expressive SOAP-style format. Maintain the original tone, flow, and personality of the note, but reorganize it to be clear and structured. Keep the storytelling style where possible while ensuring the content is concise, professional, and aligned with SOAP documentation used in physical therapy.

#     Do not rephrase excessively or make the note sound robotic — instead, enhance readability, structure, and clarity while preserving the intent and voice of the Flexologist.
#       # Steps:
#       1. What was done in the session:
#          - Identify the phase of periodization (Foundation, Active, or Performance).
#          - Retain the Flexologist's natural tone describing the work done, key stretches, muscles targeted, and observed client responses.
#          - Include details like class/session/logging number if mentioned..
#       2. Why the actions were performed:
#          - Keep the reasoning narrative-style but clarify the purpose of the techniques (e.g., improving range of motion, reducing muscle guarding, restoring balance).
#       3. Future plans:
#          - Outline the next steps or focus areas in a natural yet structured tone.
#          - Include homework, self-care, or activity recommendations if provided.
#          - Suggest additional lifestyle advice if applicable.
#       4. Identify and Highlight Missing Information:
#          - Explicitly list what key elements (Class, Phase, rationale, plan, etc.) were not mentioned.
#       5. Suggestions for Improvement:
#          - Offer constructive suggestions to improve note-taking, focusing on detail, clarity, and progression tracking.
#       # Output Format:
#         Return a JSON object with a single field "notes" that contains an array of formatted expressive note objects using the fields below:

#       {{
#         "notes": [
#                 {{
#                 "Class": "23 or Session #26",
#                 "Phase": "Active",
#                 "Today": "Expressively written summary of what was done in the session, maintaining the Flexologist's tone and details.",
#                 "Next": "Next session plan or narrative follow-up goal.",
#                 "PNF": "2-3 PNF (if mentioned)",
#                 "Homework": "Narrative-style summary of assigned stretches or recommendations.",
#                 "Recommendation": "E.g. 4x25 minutes weekly or lifestyle advice.",
#                 "Considerations": "Contextual insights or external contributing factors affecting flexibility or performance.",
#                 "Missing Information": "List of what's missing.",
#                 "Suggested Improvement": "Natural-language suggestion for how to improve the clarity and completeness of session documentation."
#                 }}
#             ]
#       }}

#       Notes:

#         - Only include a field if it was mentioned in the original notes.

#         - Preserve emotional or descriptive language (e.g., “Client felt more open through the hips after deep PNF work”).

#         - Keep the output structured but authentically human — as if a Flexologist were documenting naturally but clearly.
    

#     """
#     max_retries = 3
#     retry_delay = 8

#     for attempt in range(max_retries):
#         try:
#             response = client.chat.completions.create(
#                 model="gpt-5-mini",
#                 messages=[
#                     {
#                         "role": "system",
#                         "content": "You are a note formatter that formats notes into a structured and concise format following the format provided in the example. Focus on detailing what actions were taken during the session, why they were performed, and future plans. Ensure to exclude any 'Meeting Summary' details such as client name, Flexologist, or location. Highlight any missing information and provide suggestions for improvement in note-taking, if necessary.",
#                     },
#                     {
#                         "role": "user",
#                         "content": prompt
#                     },
#                 ],
#                 temperature=1,
#             )
#             result = response.choices[0].message.content
#             if not isinstance(result, str):
#                 raise ValueError("Response content is not a string")

#             cleaned_result = result.strip()
#             if cleaned_result.startswith("```json"):
#                 cleaned_result = cleaned_result[7:-3].strip()

#             data = json.loads(cleaned_result)

#             return data

#         except RateLimitError as e:
#             print(f"Rate limit error: {e}")
#             if attempt < max_retries - 1:
#                 wait_time = retry_delay * (2**attempt)
#                 print(f"Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
#                 time.sleep(wait_time)
#             else:
#                 print("Max retries reached")
#                 break
#         except Exception as e:
#             print(f"OpenAI error: {e}")
#             break
#     data = {"notes": ["No notes formatted error"]}

#     return data
