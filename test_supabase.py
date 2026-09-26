from supabase_client import supabase

# Login
login = supabase.auth.sign_in_with_password({
    "email": "admin@test.local",
    "password": "012012",
})

user_id = login.user.id

print("LOGIN OK")
print("User ID:", user_id)

# Ambil profil Kargo
profile = (
    supabase
    .table("user_profiles")
    .select("*")
    .eq("id", user_id)
    .single()
    .execute()
)

print("\nPROFILE:")
print(profile.data)

# Ambil akses cabang
access = (
    supabase
    .table("user_cabang_access")
    .select("*")
    .eq("id_user", user_id)
    .execute()
)

print("\nCABANG ACCESS:")
print(access.data)