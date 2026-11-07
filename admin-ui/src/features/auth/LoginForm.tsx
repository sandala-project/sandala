import { useForm } from "react-hook-form";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { TextField } from "../../components/Field";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";

type LoginValues = {
  login: string;
  password: string;
};

export function LoginForm() {
  const auth = useAuth();
  const { t } = useI18n();
  const {
    formState: { errors, isSubmitting },
    handleSubmit,
    register,
    setError,
  } = useForm<LoginValues>({
    defaultValues: {
      login: "",
      password: "",
    },
  });

  return (
    <Card
      title={
        <div>
          <strong>{t("auth.signIn")}</strong>
          <p className="card-subtitle">{t("auth.description")}</p>
        </div>
      }
    >
      <form
        className="auth-form"
        onSubmit={handleSubmit(async (values) => {
          try {
            await auth.login(values);
          } catch {
            setError("password", { message: t("errors.loginFailed") });
          }
        })}
      >
        <TextField
          autoComplete="username"
          error={errors.login?.message}
          label={t("auth.login")}
          {...register("login", { required: t("form.required.login") })}
        />
        <TextField
          autoComplete="current-password"
          error={errors.password?.message}
          label={t("auth.password")}
          type="password"
          {...register("password", { required: t("form.required.password") })}
        />
        <Button disabled={isSubmitting || auth.isLoggingIn} type="submit">
          {t("auth.login.cta")}
        </Button>
      </form>
    </Card>
  );
}
