import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AppShell } from "../layouts/AppShell";
import {
  ApiError,
  createAccessRequest,
  createBooking,
  getAvailability,
  getEquipment,
  type AvailabilityResponse,
  type Equipment,
  type TimeInterval,
} from "../utilities/api";
import { bookableSlots, formatUtcRange } from "../utilities/bookableSlots";
import { buttonClassName, cardClassName, secondaryButtonClassName, textLinkClassName } from "../utilities/classes";
import { useAuth } from "../utilities/Auth";
import { defaultProjectId, departmentName, labName } from "../utilities/demoCatalog";
import { resourceKind, resourceKindLabel } from "../utilities/resourceKind";
import { usePageTitle } from "../utilities/usePageTitle";

function defaultDate(): string {
  const now = new Date();
  now.setUTCDate(now.getUTCDate() + 1);
  return now.toISOString().slice(0, 10);
}

export function EquipmentDetailPage() {
  const { equipmentId } = useParams();
  const [equipment, setEquipment] = useState<Equipment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState(defaultDate);
  const [duration, setDuration] = useState(120);
  const [availability, setAvailability] = useState<AvailabilityResponse | null>(null);
  const [availabilityError, setAvailabilityError] = useState<string | null>(null);
  const [selected, setSelected] = useState<TimeInterval | null>(null);
  const [purpose, setPurpose] = useState("");
  const [bookingMessage, setBookingMessage] = useState<string | null>(null);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const auth = useAuth();
  const signedIn = Boolean(auth.firebaseUser);
  const role = auth.profile?.role ?? null;
  const canBook = signedIn && (role === "student" || role === "admin");
  const canRequest = signedIn && role === "student";

  usePageTitle(equipment ? `${equipment.name} · LabLink` : "Book · LabLink");

  useEffect(() => {
    if (!equipmentId) {
      return;
    }
    let cancelled = false;
    getEquipment(equipmentId)
      .then((item) => {
        if (!cancelled) {
          setEquipment(item);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "This item could not be loaded.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [equipmentId]);

  useEffect(() => {
    if (!equipmentId || !date || !signedIn) {
      return;
    }
    let cancelled = false;
    setAvailability(null);
    setSelected(null);
    getAvailability(equipmentId, date)
      .then((result) => {
        if (!cancelled) {
          setAvailability(result);
          setAvailabilityError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setAvailabilityError(caught instanceof ApiError ? caught.message : "Availability could not be loaded.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [equipmentId, date, signedIn]);

  const slots = useMemo(
    () => (availability ? bookableSlots(availability.available, duration) : []),
    [availability, duration],
  );

  async function refreshAvailability(): Promise<void> {
    if (!equipmentId) {
      return;
    }
    const next = await getAvailability(equipmentId, date);
    setAvailability(next);
    setSelected(null);
  }

  async function onConfirm(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!equipmentId || !selected) {
      return;
    }
    setSubmitting(true);
    setBookingMessage(null);
    setBookingError(null);
    try {
      const note = purpose.trim();
      const created = await createBooking({
        equipment_id: equipmentId,
        project_id: defaultProjectId(equipment?.department_id ?? ""),
        start: selected.start,
        end: selected.end,
        ...(note ? { purpose: note } : {}),
      });
      setBookingMessage(
        `${created.equipment_name ?? created.equipment_id} is booked ${formatUtcRange(created.start, created.end)}. Cancel anytime from My bookings.`,
      );
      await refreshAvailability();
      setPurpose("");
    } catch (caught: unknown) {
      setBookingError(caught instanceof ApiError ? caught.message : "The booking could not be created.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onRequestAccess(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!equipmentId || !selected) {
      return;
    }
    setSubmitting(true);
    setBookingMessage(null);
    setBookingError(null);
    try {
      const created = await createAccessRequest({
        equipment_id: equipmentId,
        project_id: defaultProjectId(equipment?.department_id ?? ""),
        justification: purpose.trim() || "Please approve this time slot.",
        start: selected.start,
        end: selected.end,
      });
      setBookingMessage(`Request sent (${created.status}). A faculty member must approve before this time is booked.`);
    } catch (caught: unknown) {
      setBookingError(caught instanceof ApiError ? caught.message : "The access request could not be submitted.");
    } finally {
      setSubmitting(false);
    }
  }

  if (error) {
    return (
      <AppShell title="Book">
        <ErrorState title="Item not found" message={error}>
          <Link className={textLinkClassName} to="/equipment">
            Back to catalog
          </Link>
        </ErrorState>
      </AppShell>
    );
  }

  if (!equipment) {
    return (
      <AppShell title="Book">
        <LoadingState label="Loading item" />
      </AppShell>
    );
  }

  const kind = resourceKind(equipment);
  const restricted = equipment.safety_prerequisites.length > 0;
  const catalogOperational = equipment.status === "available";

  return (
    <AppShell title={equipment.name}>
      <p className="text-sm text-muted">
        {resourceKindLabel(kind)} · {departmentName(equipment.department_id)} · {labName(equipment.lab_id)}
      </p>
      <p className="mt-2 capitalize text-accent">Catalog status: {equipment.status}</p>
      <p className="mt-4 max-w-3xl leading-7 text-ink">{equipment.description}</p>

      <section className={`${cardClassName} mt-8`} aria-labelledby="book-title">
        <h2 id="book-title" className="font-display text-2xl text-primary">
          Book
        </h2>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-muted">
          <li>Pick a date</li>
          <li>Choose a free time</li>
          <li>Add an optional note and confirm</li>
        </ol>
        {!signedIn ? (
          <p className="mt-3 text-sm">
            <Link className={textLinkClassName} to="/login">
              Sign in to book
            </Link>
          </p>
        ) : null}
        {signedIn && !canBook && !restricted ? (
          <p className="mt-3 text-sm text-muted">Booking is for student accounts. Faculty use review instead.</p>
        ) : null}
        {!catalogOperational ? (
          <p className="mt-3 text-sm" role="status">
            This item is {equipment.status}, so it cannot be booked.
          </p>
        ) : null}
        {restricted ? (
          <p className="mt-3 rounded-xl bg-aqua px-4 py-3 text-sm text-primary">
            This item needs faculty approval. Choose a time, add a short reason, and send a request. The slot is not
            booked until a faculty member approves.
          </p>
        ) : null}

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="block text-sm font-medium text-primary">
            Date
            <input
              className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
              type="date"
              value={date}
              onChange={(event) => {
                setDate(event.target.value);
              }}
            />
          </label>
          <label className="block text-sm font-medium text-primary">
            Length
            <select
              className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
              value={duration}
              onChange={(event) => {
                setDuration(Number(event.target.value));
                setSelected(null);
              }}
            >
              <option value={60}>1 hour</option>
              <option value={120}>2 hours</option>
            </select>
          </label>
        </div>

        {!signedIn ? null : availabilityError ? (
          <p className="mt-3 text-sm" role="alert">
            {availabilityError}
          </p>
        ) : availability === null ? (
          <div className="mt-3">
            <LoadingState label="Loading free times" />
          </div>
        ) : slots.length === 0 ? (
          <div className="mt-3">
            <EmptyState title="No free times" description="Nothing is free on this date for that length. Try another date." />
          </div>
        ) : (
          <div className="mt-4">
            <h3 className="text-sm font-medium text-primary">Free times</h3>
            <ul className="mt-2 grid list-none gap-2 p-0 sm:grid-cols-2">
              {slots.map((slot) => {
                const active = selected?.start === slot.start && selected?.end === slot.end;
                return (
                  <li key={`${slot.start}-${slot.end}`}>
                    <button
                      className={active ? buttonClassName : `${secondaryButtonClassName} w-full`}
                      type="button"
                      disabled={!catalogOperational}
                      onClick={() => {
                        setSelected(slot);
                        setBookingMessage(null);
                        setBookingError(null);
                      }}
                    >
                      {formatUtcRange(slot.start, slot.end)}
                    </button>
                  </li>
                );
              })}
            </ul>
            {availability.unavailable.length > 0 ? (
              <p className="mt-3 text-sm text-muted">
                Already booked:{" "}
                {availability.unavailable.map((item) => formatUtcRange(item.start, item.end)).join("; ")}
              </p>
            ) : null}
          </div>
        )}

        <form className="mt-4 grid gap-3" onSubmit={restricted ? onRequestAccess : onConfirm}>
          <label className="block text-sm font-medium text-primary">
            Purpose (optional)
            <input
              className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
              type="text"
              maxLength={200}
              value={purpose}
              onChange={(event) => {
                setPurpose(event.target.value);
              }}
              placeholder="Short note, if you want"
            />
          </label>
          <button
            className={`${buttonClassName} w-fit`}
            type="submit"
            disabled={submitting || !selected || !catalogOperational || (restricted ? !canRequest : !canBook)}
          >
            {submitting ? "Working…" : restricted ? "Request approval" : "Confirm booking"}
          </button>
        </form>
        {bookingMessage ? (
          <p className="mt-3 text-sm text-signal" role="status">
            {bookingMessage}
          </p>
        ) : null}
        {bookingError ? (
          <p className="mt-3 text-sm" role="alert">
            {bookingError}
          </p>
        ) : null}
        <p className="mt-4 text-sm">
          <Link className={textLinkClassName} to="/bookings">
            My bookings
          </Link>
        </p>
      </section>
    </AppShell>
  );
}
