"""Authentication, session, onboarding, and learner-profile routes."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import uuid4

import bcrypt
import psycopg2
from flask import Response, request, session

from backend import db_store
from backend.config import PROFILE_GENDER_CHOICES
from backend.graph_engine import GraphValidationError
from backend.routes.responses import error, success


def register_account_routes(app: Any, services: Any) -> None:
    """Register account-related API endpoints on ``app``."""

    ai_service = services.ai_service

    @app.post("/api/register")
    def register():
        """Create an account, requiring an explicit login afterwards."""

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error("Request body must be JSON")

        email = body.get("email")
        password = body.get("password")
        if not isinstance(email, str) or not re.fullmatch(
            r"[^\s@]+@[^\s@]+\.[^\s@]+",
            email.strip(),
        ):
            return error("Enter a valid email address")
        if not isinstance(password, str) or len(password) < 8:
            return error("Password must contain at least 8 characters")

        normalized_email = email.strip().lower()
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(),
        ).decode("utf-8")
        conn = None
        try:
            conn = services.get_db()
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (uid, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, uid, email
                    """,
                    (uuid4().hex[:12], normalized_email, password_hash),
                )
                user_id, uid, user_email = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO user_profiles (user_id, display_name)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (user_id, user_email.split("@", 1)[0]),
                )
            conn.commit()
            session.clear()
            return success(
                {
                    "id": user_id,
                    "uid": uid,
                    "email": user_email,
                    "redirect": "/login",
                },
                "Account created. Please log in.",
                201,
            )
        except psycopg2.IntegrityError:
            if conn is not None:
                conn.rollback()
            return error("This email is already registered", 409)
        except psycopg2.Error as exc:
            if conn is not None:
                conn.rollback()
            return error("Database connection failed", 500, str(exc))
        finally:
            if conn is not None:
                conn.close()

    @app.post("/api/login")
    def login():
        """Authenticate a user and select the correct next page."""

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error("Request body must be JSON")

        email = body.get("email")
        password = body.get("password")
        if not isinstance(email, str) or not email.strip():
            return error("Email must be a non-empty string")
        if not isinstance(password, str) or not password:
            return error("Password must be a non-empty string")

        conn = None
        try:
            conn = services.get_db()
            db_store.ensure_schema(conn)
            conn.commit()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, email, password_hash, uid
                    FROM users
                    WHERE email = %s
                    """,
                    (email.strip().lower(),),
                )
                user = cur.fetchone()

                if user is None:
                    return error("Email หรือ Password ไม่ถูกต้อง", 401)

                user_id, user_email, password_hash, uid = user
                password_correct = bcrypt.checkpw(
                    password.encode("utf-8"),
                    password_hash.encode("utf-8"),
                )
                if not password_correct:
                    return error("Email หรือ Password ไม่ถูกต้อง", 401)

                # Reuse this connection. The old implementation opened a
                # second one here and leaked the first pooled connection.
                cur.execute(
                    """
                    SELECT favorite_animal, favorite_color, gender
                    FROM user_profiles
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                profile = cur.fetchone()

            session["user_id"] = int(user_id)
            session["uid"] = uid
            session["email"] = user_email
            redirect_path = (
                "/onboarding"
                if not profile or any(value is None for value in profile)
                else "/roadmap"
            )
            return success(
                {
                    "id": user_id,
                    "uid": uid,
                    "email": user_email,
                    "redirect": redirect_path,
                },
                "Login สำเร็จ",
            )
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        finally:
            if conn is not None:
                conn.close()

    @app.get("/api/me")
    def current_user():
        """Return the signed-in user and public profile fields."""

        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("ยังไม่ได้ Login", 401)

        conn = None
        try:
            conn = services.get_db()
            db_store.ensure_schema(conn)
            conn.commit()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        u.id,
                        u.uid,
                        u.email,
                        p.display_name,
                        p.level,
                        p.current_exp,
                        p.current_career_id,
                        p.favorite_animal,
                        p.favorite_color,
                        p.gender,
                        p.profile_picture
                    FROM users u
                    LEFT JOIN user_profiles p ON p.user_id = u.id
                    WHERE u.id = %s
                    """,
                    (user_id,),
                )
                user = cur.fetchone()

            if user is None:
                session.clear()
                return error("User not found", 404)

            (
                user_id,
                uid,
                email,
                display_name,
                level,
                current_exp,
                current_career_id,
                favorite_animal,
                favorite_color,
                gender,
                profile_picture,
            ) = user
            profile_image, generated = services.profile_image_data_url(
                profile_picture
            )
            return success(
                {
                    "id": user_id,
                    "uid": uid,
                    "email": email,
                    "displayName": display_name,
                    "level": level,
                    "currentExp": current_exp,
                    "currentCareerId": current_career_id,
                    "favoriteAnimal": favorite_animal,
                    "favoriteColor": favorite_color,
                    "gender": gender,
                    "profileImage": profile_image,
                    "profileImageGenerated": generated,
                }
            )
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        finally:
            if conn is not None:
                conn.close()

    @app.put("/api/profile")
    def update_profile():
        """Update editable profile fields and generate a missing portrait."""

        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error("Request body must be JSON")

        display_name = body.get("displayName")
        current_career_id = body.get("currentCareerId")
        favorite_animal = body.get("favoriteAnimal")
        favorite_color = body.get("favoriteColor")
        gender = body.get("gender")

        if display_name is not None and (
            not isinstance(display_name, str)
            or not display_name.strip()
            or len(display_name) > 80
        ):
            return error("displayName must be 1 to 80 characters")

        profile_fields = {
            "favoriteAnimal": favorite_animal,
            "favoriteColor": favorite_color,
            "gender": gender,
        }
        for field_name, value in profile_fields.items():
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                return error(f"{field_name} must be a non-empty string")
        if isinstance(gender, str) and gender.strip() not in PROFILE_GENDER_CHOICES:
            return error("gender must be one of the supported choices")

        if current_career_id is not None:
            if isinstance(current_career_id, str) and current_career_id.isdigit():
                current_career_id = int(current_career_id)
            if not isinstance(current_career_id, int) or current_career_id <= 0:
                return error("currentCareerId must be a valid career id")
            conn = services.get_db()
            try:
                db_store.ensure_schema(conn)
                if not db_store.career_exists(conn, current_career_id):
                    return error("Career not found", 404, current_career_id)
            finally:
                conn.close()

        if all(
            value is None
            for value in (
                display_name,
                current_career_id,
                favorite_animal,
                favorite_color,
                gender,
            )
        ):
            return error(
                "Provide displayName, currentCareerId, or onboarding answers"
            )

        conn = None
        try:
            conn = services.get_db()
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(67341, %s)", (user_id,))
                normalized_name = (
                    display_name.strip() if isinstance(display_name, str) else None
                )
                insert_name = (
                    normalized_name
                    or db_store.user_display_name(conn, user_id)
                    or "Learner"
                )
                answers = {
                    "favorite_animal": (
                        favorite_animal.strip()
                        if isinstance(favorite_animal, str)
                        else None
                    ),
                    "favorite_color": (
                        favorite_color.strip()
                        if isinstance(favorite_color, str)
                        else None
                    ),
                    "gender": gender.strip() if isinstance(gender, str) else None,
                }
                cur.execute(
                    """
                    INSERT INTO user_profiles (
                        user_id,
                        display_name,
                        current_career_id,
                        favorite_animal,
                        favorite_color,
                        gender
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        display_name = COALESCE(%s, user_profiles.display_name),
                        current_career_id = COALESCE(
                            EXCLUDED.current_career_id,
                            user_profiles.current_career_id
                        ),
                        favorite_animal = COALESCE(
                            EXCLUDED.favorite_animal,
                            user_profiles.favorite_animal
                        ),
                        favorite_color = COALESCE(
                            EXCLUDED.favorite_color,
                            user_profiles.favorite_color
                        ),
                        gender = COALESCE(EXCLUDED.gender, user_profiles.gender),
                        updated_at = NOW()
                    RETURNING
                        display_name,
                        current_career_id,
                        favorite_animal,
                        favorite_color,
                        gender,
                        profile_picture
                    """,
                    (
                        user_id,
                        insert_name,
                        current_career_id,
                        answers["favorite_animal"],
                        answers["favorite_color"],
                        answers["gender"],
                        normalized_name,
                    ),
                )
                name, career_id, animal, color, gender_value, picture = cur.fetchone()

                cur.execute(
                    """
                    SELECT a.title
                    FROM user_achievements ua
                    JOIN achievements a ON a.id = ua.achievement_id
                    WHERE ua.user_id = %s
                    ORDER BY ua.unlocked_at
                    """,
                    (user_id,),
                )
                achievement_names = [row[0] for row in cur.fetchall()]

                answers_changed = any(
                    value is not None
                    for value in (favorite_animal, favorite_color, gender)
                )
                answers_complete = all(
                    isinstance(value, str) and bool(value.strip())
                    for value in (animal, color, gender_value)
                )
                _, portrait_generated = services.profile_image_data_url(picture)
                if answers_changed and answers_complete and not portrait_generated:
                    payload = {
                        "favoriteAnimal": animal,
                        "favoriteColor": color,
                        "gender": gender_value,
                    }
                    prompt = ai_service.build_profile_prompt(
                        payload,
                        achievement_names,
                    )
                    image_bytes = ai_service.generate_profile_image(
                        payload,
                        achievement_names,
                        prompt=prompt,
                        allow_fallback=False,
                    )
                    cur.execute(
                        """
                        UPDATE user_profiles
                        SET profile_prompt = %s,
                            profile_picture = %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (prompt, image_bytes, user_id),
                    )
            conn.commit()
            return success(
                {
                    "displayName": name,
                    "currentCareerId": career_id,
                    "favoriteAnimal": animal,
                    "favoriteColor": color,
                    "gender": gender_value,
                },
                "Profile updated",
            )
        except ai_service.ProfileImageGenerationError as exc:
            if conn is not None:
                conn.rollback()
            return error(
                "Profile image generation failed. Please try again.",
                502,
                str(exc),
            )
        except psycopg2.Error as exc:
            if conn is not None:
                conn.rollback()
            return error("Database connection failed", 500, str(exc))
        finally:
            if conn is not None:
                conn.close()

    @app.get("/api/profile/avatar")
    def profile_avatar():
        """Serve the learner's generated portrait with private revalidation."""

        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        conn = services.get_db()
        try:
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT profile_picture
                    FROM user_profiles
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
            if row is None or not row[0]:
                return error("Profile picture not set", 404)

            image_bytes = bytes(row[0])
            mime_type = ai_service.profile_image_mime_type(image_bytes)
            if mime_type is None or mime_type == "image/svg+xml":
                return error("Profile picture is not a generated portrait", 404)

            etag = hashlib.md5(image_bytes).hexdigest()
            headers = {
                "Cache-Control": "private, no-cache",
                "ETag": f'"{etag}"',
            }
            if request.if_none_match.contains(etag):
                return Response(status=304, headers=headers)
            return Response(image_bytes, mimetype=mime_type, headers=headers)
        finally:
            conn.close()

    @app.get("/api/profile/highest-achievement")
    def highest_profile_achievement():
        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        conn = services.get_db()
        try:
            db_store.ensure_schema(conn)
            highest = services.highest_career_achievement_for_user(conn, user_id)
            conn.commit()
            return success(highest, "Highest career achievement loaded")
        except (GraphValidationError, KeyError, ValueError) as exc:
            conn.rollback()
            return error(
                "Could not calculate career achievement",
                500,
                str(exc),
            )
        except psycopg2.Error as exc:
            conn.rollback()
            return error("Database connection failed", 500, str(exc))
        finally:
            conn.close()

    @app.get("/api/profile/onboarding")
    def onboarding_status():
        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        conn = services.get_db()
        try:
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT favorite_animal, favorite_color, gender, profile_picture
                    FROM user_profiles
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
            if row is None:
                return success({"required": True})
            _, portrait_generated = services.profile_image_data_url(row[3])
            return success(
                {
                    "required": (
                        row[0] is None
                        or row[1] is None
                        or row[2] is None
                        or not portrait_generated
                    )
                }
            )
        finally:
            conn.close()

    @app.post("/api/profile/onboarding")
    def onboarding_submit():
        """Save first-login answers and generate the profile portrait."""

        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error("Request body must be JSON")

        answers = {
            "favoriteAnimal": body.get("favoriteAnimal"),
            "favoriteColor": body.get("favoriteColor"),
            "gender": body.get("gender"),
        }
        for key, value in answers.items():
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value.strip()) > 80
            ):
                return error(f"{key} must be 1 to 80 characters")
            answers[key] = value.strip()
        if answers["gender"] not in PROFILE_GENDER_CHOICES:
            return error("gender must be one of the supported choices")

        conn = services.get_db()
        try:
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(67341, %s)", (user_id,))
                cur.execute(
                    """
                    SELECT profile_picture
                    FROM user_profiles
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                existing_profile = cur.fetchone()
                _, generated = services.profile_image_data_url(
                    existing_profile[0] if existing_profile else None
                )
                if generated:
                    return error(
                        "Profile picture can only be generated once per account",
                        409,
                    )
                cur.execute(
                    """
                    SELECT a.title
                    FROM user_achievements ua
                    JOIN achievements a ON a.id = ua.achievement_id
                    WHERE ua.user_id = %s
                    ORDER BY ua.unlocked_at
                    """,
                    (user_id,),
                )
                achievements = [row[0] for row in cur.fetchall()]

            prompt = ai_service.build_profile_prompt(answers, achievements)
            image_bytes = ai_service.generate_profile_image(
                answers,
                achievements,
                prompt=prompt,
                allow_fallback=False,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_profiles (
                        user_id,
                        display_name,
                        favorite_animal,
                        favorite_color,
                        gender,
                        profile_prompt,
                        profile_picture
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        favorite_animal = EXCLUDED.favorite_animal,
                        favorite_color = EXCLUDED.favorite_color,
                        gender = EXCLUDED.gender,
                        profile_prompt = EXCLUDED.profile_prompt,
                        profile_picture = EXCLUDED.profile_picture,
                        updated_at = NOW()
                    RETURNING favorite_animal, favorite_color, gender
                    """,
                    (
                        user_id,
                        db_store.user_display_name(conn, user_id) or "Learner",
                        answers["favoriteAnimal"],
                        answers["favoriteColor"],
                        answers["gender"],
                        prompt,
                        image_bytes,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            profile_image, _ = services.profile_image_data_url(image_bytes)
            return success(
                {
                    "favoriteAnimal": row[0],
                    "favoriteColor": row[1],
                    "gender": row[2],
                    "profileImage": profile_image,
                    "profileImageGenerated": True,
                },
                "Onboarding completed",
            )
        except ai_service.ProfileImageGenerationError as exc:
            conn.rollback()
            return error(
                "Profile image generation failed. Please try again.",
                502,
                str(exc),
            )
        except psycopg2.Error as exc:
            conn.rollback()
            return error("Database connection failed", 500, str(exc))
        finally:
            conn.close()

    @app.post("/api/profile/refresh")
    def refresh_profile_portrait():
        """Generate a portrait for an account still missing a real image."""

        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        conn = services.get_db()
        try:
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(67341, %s)", (user_id,))
                cur.execute(
                    """
                    SELECT profile_picture
                    FROM user_profiles
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                existing_profile = cur.fetchone()
                _, generated = services.profile_image_data_url(
                    existing_profile[0] if existing_profile else None
                )
                if generated:
                    return error(
                        "Profile picture can only be generated once per account",
                        409,
                    )

            refreshed = services.refresh_user_profile_portrait(
                user_id,
                conn,
                require_generated=True,
            )
            conn.commit()
            if not refreshed:
                return error("Profile onboarding answers are not set yet", 400)
            return success({"refreshed": True}, "Profile portrait refreshed")
        except ai_service.ProfileImageGenerationError as exc:
            conn.rollback()
            return error(
                "Profile image generation failed. Please try again.",
                502,
                str(exc),
            )
        except psycopg2.Error as exc:
            conn.rollback()
            return error("Database connection failed", 500, str(exc))
        finally:
            conn.close()

    @app.post("/api/logout")
    def logout():
        session.clear()
        return success(message="Logout สำเร็จ")
