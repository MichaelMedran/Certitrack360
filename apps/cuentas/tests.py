"""Pruebas de usuarios, roles y accesos (SDD RF-01, RF-02, RF-18; casos 1 y 2 de la sección 17.2)."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

Usuario = get_user_model()


class RolYPanelTecnicoTests(TestCase):
    def test_solo_el_rol_admin_es_staff(self):
        for rol, esperado in (("JUNIOR", False), ("SENIOR", False), ("GERENTE", False), ("ADMIN", True)):
            with self.subTest(rol=rol):
                u = Usuario.objects.create_user(f"u_{rol}", password="x", rol=rol)
                self.assertEqual((u.is_staff, u.is_superuser), (esperado, esperado))

    def test_cambiar_el_rol_da_o_quita_el_acceso_al_panel(self):
        u = Usuario.objects.create_user("cambia", password="x", rol="SENIOR")
        u.rol = "ADMIN"
        u.save()
        u.refresh_from_db()
        self.assertTrue(u.is_staff and u.is_superuser)
        u.rol = "GERENTE"
        u.save()
        u.refresh_from_db()
        self.assertFalse(u.is_staff or u.is_superuser)

    def test_createsuperuser_crea_un_admin(self):
        u = Usuario.objects.create_superuser("root", "root@demo.invalid", "x")
        self.assertEqual(u.rol, "ADMIN")
        self.assertTrue(u.is_superuser and u.is_staff)

    def test_el_panel_tecnico_es_solo_para_admin(self):
        esperado = {"JUNIOR": 302, "SENIOR": 302, "GERENTE": 302, "ADMIN": 200}  # 302 = a la pantalla de ingreso del panel
        for rol, codigo in esperado.items():
            with self.subTest(rol=rol):
                self.client.force_login(Usuario.objects.create_user(f"p_{rol}", password="x", rol=rol))
                r = self.client.get("/admin/")
                self.assertEqual(r.status_code, codigo)
                if rol != "ADMIN":
                    self.assertIn("/admin/login/", r["Location"])

    def test_el_panel_lista_los_usuarios_para_el_admin(self):
        self.client.force_login(Usuario.objects.create_user("el_admin", password="x", rol="ADMIN"))
        self.assertEqual(self.client.get("/admin/cuentas/usuario/").status_code, 200)


class SesionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = {rol: Usuario.objects.create_user(f"s_{rol}", password="clave-de-prueba", rol=rol,
                                                         first_name=rol.title())
                        for rol in ("JUNIOR", "SENIOR", "GERENTE", "ADMIN")}

    def test_las_rutas_son_las_del_sdd(self):
        self.assertEqual((reverse("login"), reverse("logout")), ("/login/", "/logout/"))

    def test_los_cuatro_roles_inician_y_cierran_sesion(self):
        for rol, usuario in self.usuarios.items():
            with self.subTest(rol=rol):
                c = Client()
                r = c.post(reverse("login"), {"username": usuario.username, "password": "clave-de-prueba"})
                self.assertRedirects(r, reverse("inicio"))
                self.assertEqual(c.get(reverse("inicio")).status_code, 200)
                c.post(reverse("logout"))
                self.assertEqual(c.get(reverse("inicio")).status_code, 302)

    def test_credenciales_incorrectas(self):
        r = self.client.post(reverse("login"), {"username": "s_JUNIOR", "password": "mala"})
        self.assertContains(r, "Usuario o contraseña incorrectos")

    def test_cada_rol_ve_la_navegacion_que_le_corresponde(self):
        for rol, usuario in self.usuarios.items():
            with self.subTest(rol=rol):
                self.client.force_login(usuario)
                html = self.client.get(reverse("inicio")).content.decode()
                for ruta in (reverse("tablero"), reverse("calendario"), reverse("entregables"), reverse("asistente")):
                    self.assertIn(f'href="{ruta}"', html)
                self.assertEqual(f'href="{reverse("administracion")}"' in html, rol in ("GERENTE", "ADMIN"))

    def test_la_sesion_se_cierra_por_inactividad(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, settings.SESSION_IDLE_MINUTES * 60)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)  # cada petición renueva el plazo

    def test_validadores_de_contrasena_activos(self):
        nombres = [v["NAME"].rsplit(".", 1)[1] for v in settings.AUTH_PASSWORD_VALIDATORS]
        self.assertEqual(set(nombres), {"UserAttributeSimilarityValidator", "MinimumLengthValidator",
                                        "CommonPasswordValidator", "NumericPasswordValidator"})

    def test_las_contrasenas_se_guardan_con_hash_seguro(self):
        # Las pruebas usan un hash rápido (ver settings.py); aquí se comprueba el que usa la aplicación real.
        with override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher"]):
            u = Usuario.objects.create_user("con_hash", password="clave-de-prueba", rol="JUNIOR")
        self.assertNotIn("clave-de-prueba", u.password)
        self.assertTrue(u.password.startswith("pbkdf2_sha256$"))

    def test_el_hash_rapido_solo_existe_al_correr_las_pruebas(self):
        fuente = (Path(settings.BASE_DIR) / "certitrack" / "settings.py").read_text(encoding="utf-8")
        self.assertEqual(fuente.count("PASSWORD_HASHERS"), 1)
        self.assertRegex(fuente, r'if "test" in sys\.argv:\n    PASSWORD_HASHERS = \["django\.contrib\.auth\.hashers\.MD5PasswordHasher"\]')


class RutasProtegidasTests(TestCase):
    """«Todas las rutas, salvo el inicio de sesión, requieren autenticación» (SDD §14)."""

    def rutas(self):
        solo_lectura = [
            reverse(n) for n in ("inicio", "tablero", "entregables", "entregable_nuevo", "calendario", "calendario_eventos",
                                 "notificaciones", "asistente", "administracion")
        ] + [
            reverse("entregable_detalle", args=[1]), reverse("adjunto_descargar", args=[1]),
            reverse("adm_editar", args=["clientes", 1]),
        ] + [reverse(n, args=[e]) for e in ("clientes", "contratos", "plantillas") for n in ("adm_lista", "adm_nuevo")]
        con_post = [
            reverse("entregable_estado", args=[1]), reverse("observacion_nueva", args=[1]),
            reverse("observacion_resolver", args=[1]), reverse("adjunto_subir", args=[1]),
            reverse("adjunto_eliminar", args=[1]), reverse("tablero_mover", args=[1]),
            reverse("notificaciones_leidas"), reverse("notificacion_leer", args=[1]),
        ]
        return [("get", r) for r in solo_lectura] + [("post", r) for r in con_post]

    def test_sin_sesion_todo_redirige_al_ingreso(self):
        for metodo, ruta in self.rutas():
            with self.subTest(ruta=ruta, metodo=metodo):
                r = getattr(self.client, metodo)(ruta)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r["Location"].startswith(reverse("login")), r["Location"])

    def test_el_ingreso_es_publico(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_los_formularios_exigen_csrf(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(Usuario.objects.create_user("gerente_csrf", password="x", rol="GERENTE"))
        for ruta in (reverse("entregable_estado", args=[1]), reverse("notificaciones_leidas"),
                     reverse("notificacion_leer", args=[1]), reverse("adjunto_eliminar", args=[1]),
                     reverse("adjunto_subir", args=[1]), reverse("tablero_mover", args=[1])):
            with self.subTest(ruta=ruta):
                self.assertEqual(c.post(ruta).status_code, 403)
